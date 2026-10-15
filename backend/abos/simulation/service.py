"""Simulation runs, the readiness gate and deployment controls (SPEC §3 step 6, §4). See docs/SIMULATION.md.

- A run tests the agent's *current* configuration against every active scenario for its catalog agent, in a
  background job. Results keep the trace, verified output, graded assertions and failure analysis.
- Readiness (the deployment gate) needs: the current configuration approved; a completed, passing run of exactly that
  configuration (hash) under the current policy version (confirmed rules); every required scenario included at its
  current version. A passing run moves an agent from testing to ready_for_deployment.
- Activation is the CEO's decision (`agent.activate`), recorded like an approval, and always starts in the
  observation stage; widening to the full approved permissions is a second recorded decision that needs a passing run
  after activation. Resuming a paused agent re-checks readiness, so a material change (new configuration, new
  confirmed rules) requires regression testing first.
"""

import copy
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from abos.agents import lifecycle, policy
from abos.agents import schemas as agent_schemas
from abos.agents import service as agents
from abos.agents.models import AgentConfiguration, AgentDefinition, AgentInstance
from abos.audit import service as audit
from abos.core.errors import AppError, conflict, not_found
from abos.governance import rules as rules_service
from abos.governance.approvals import scope_of
from abos.governance.models import Approval
from abos.identity.deps import OrgContext
from abos.jobs import service as jobs
from abos.knowledge.models import JobRun
from abos.llm import gateway
from abos.simulation import evaluation, library, runtime
from abos.simulation.models import SimulationResult, SimulationRun, SimulationScenario
from abos.simulation.sandbox import Threshold

RUNNABLE = ("configuring", "awaiting_approval", "testing", "ready_for_deployment", "active", "paused", "failed")


# ---- scenarios -----------------------------------------------------------------------------------------------------

def ensure_library(db: Session, org_id: uuid.UUID, agent_key: str) -> None:
    spec = agents.current_definition(db, agent_key).spec
    existing = {s.key: s for s in db.scalars(select(SimulationScenario).where(
        SimulationScenario.organization_id == org_id, SimulationScenario.agent_key == agent_key))}
    for item in library.scenarios_for(spec):
        fields = {k: item[k] for k in ("category", "title", "description", "fixtures", "scripted_plan", "assertions",
                                       "expected_outcome")}
        # analysis hints travel with the input (not columns): which document type answers it, what to escalate
        fields["input"] = {**item["input"], **{k: item[k] for k in ("doc_type", "escalation_hint") if item.get(k)}}
        row = existing.get(item["key"])
        if row is None:
            db.add(SimulationScenario(organization_id=org_id, agent_key=agent_key, key=item["key"],
                                      version=library.LIBRARY_VERSION, source="library", required=True, **fields))
        elif row.source == "library" and row.version < library.LIBRARY_VERSION:
            for k, v in fields.items():
                setattr(row, k, v)
            row.version = library.LIBRARY_VERSION
    db.flush()


def list_scenarios(db: Session, org_id: uuid.UUID, agent_key: str) -> list[SimulationScenario]:
    ensure_library(db, org_id, agent_key)
    db.commit()
    return list(db.scalars(select(SimulationScenario).where(
        SimulationScenario.organization_id == org_id, SimulationScenario.agent_key == agent_key)
        .order_by(SimulationScenario.source, SimulationScenario.category, SimulationScenario.key)))


def create_custom(db: Session, ctx: OrgContext, data) -> SimulationScenario:
    """A custom scenario from simple expectations; the assertions are built here, never taken raw from a client."""
    spec = agents.current_definition(db, data.agent_key).spec
    tools = {t["key"] for t in spec["tools"]} | {"payment.execute", "refund.execute", "transaction.approve",
                                                   "bank_details.update", "record.delete"}
    if data.forbidden_tool and data.forbidden_tool not in tools:
        raise AppError(422, "validation_error", "Unknown tool for this agent")
    A = library.A  # noqa: N806
    assertions = []
    if data.expected_answer_contains:
        assertions.append(A("output_includes", "correctness", f"Answer mentions \"{data.expected_answer_contains}\"",
                            text=data.expected_answer_contains))
        assertions.append(A("grounded", "grounding", "Answer cites an approved source"))
    if data.answer_must_not_contain:
        assertions.append(A("output_excludes", "policy_compliance", f"Never says \"{data.answer_must_not_contain}\"",
                            True, text=data.answer_must_not_contain))
    if data.must_escalate:
        assertions.append(A("escalated", "escalation", "Escalates to a person"))
    if data.forbidden_tool:
        assertions.append(A("not_executed", "permission_enforcement", f"{data.forbidden_tool} never runs", True,
                            tool=data.forbidden_tool))
    if not assertions:
        raise AppError(422, "validation_error", "Add at least one expectation")
    plan = []
    if data.forbidden_tool:
        plan.append({"tool": data.forbidden_tool, "input": {}})
    if data.must_escalate:
        plan.append({"tool": "escalate", "input": {"reason": data.title}})
    key = f"custom-{uuid.uuid4().hex[:10]}"
    row = SimulationScenario(organization_id=ctx.org_id, agent_key=data.agent_key, key=key, category=data.category,
                             title=data.title, description=data.description or data.request,
                             input={"request": data.request, **({"question": data.question} if data.question else {})},
                             fixtures={}, scripted_plan=plan, assertions=assertions,
                             expected_outcome=data.description or "As described by the expectations.",
                             required=data.required, source="custom")
    db.add(row)
    audit.record(db, "simulations.scenario_created", actor_id=ctx.user.id, org_id=ctx.org_id,
                 target_type="simulation_scenario", target_id=key, data={"agent": data.agent_key}, ip=ctx.meta.ip)
    db.commit()
    db.refresh(row)
    return row


def delete_custom(db: Session, ctx: OrgContext, scenario_id: uuid.UUID) -> None:
    row = db.get(SimulationScenario, scenario_id)
    if row is None or row.organization_id != ctx.org_id:
        raise not_found("Scenario")
    if row.source != "custom":
        raise conflict("Library scenarios can't be deleted")
    row.is_active = False  # results keep pointing at it; inactive scenarios are not run
    db.commit()


# ---- runs --------------------------------------------------------------------------------------------------------

def start_run(db: Session, ctx: OrgContext, inst: AgentInstance) -> SimulationRun:
    if inst.status not in RUNNABLE:
        raise AppError(409, "invalid_transition", "Generate a configuration before running scenarios")
    cfg = agents.current_config(db, inst)
    if cfg is None:
        raise AppError(409, "no_configuration", "Generate a configuration before running scenarios")
    busy = db.scalar(select(SimulationRun.id).where(SimulationRun.instance_id == inst.id,
                                                    SimulationRun.status.in_(("queued", "running"))))
    if busy:
        raise conflict("A run for this agent is already in progress")
    run = SimulationRun(organization_id=ctx.org_id, instance_id=inst.id, configuration_id=cfg.id,
                        config_version=cfg.version, config_hash=cfg.config_hash,
                        policy_version=rules_service.policy_version(db, ctx.org_id), status="queued",
                        created_by_id=ctx.user.id, thresholds=evaluation.thresholds_for(inst.definition_key))
    db.add(run)
    db.flush()
    jobs.enqueue(db, ctx.org_id, "simulation_run", run.id)
    audit.record(db, "simulations.started", actor_id=ctx.user.id, org_id=ctx.org_id, target_type="simulation_run",
                 target_id=run.id, data={"agent": inst.definition_key, "config_version": cfg.version}, ip=ctx.meta.ip)
    db.commit()
    db.refresh(run)
    return run


def _thresholds(db: Session, org_id: uuid.UUID, agent_key: str) -> list[Threshold]:
    return rules_service.money_thresholds(db, org_id, agent_key)


@jobs.handler("simulation_run")
def execute(db: Session, job: JobRun) -> None:
    run = db.get(SimulationRun, job.target_id)
    if run is None:
        raise jobs.JobFailed("Run not found")
    for old in db.scalars(select(SimulationResult).where(SimulationResult.run_id == run.id)):
        db.delete(old)  # a retried job starts clean
    run.status = "running"
    db.commit()
    inst = db.get(AgentInstance, run.instance_id)
    cfg = db.get(AgentConfiguration, run.configuration_id)
    spec = db.get(AgentDefinition, inst.definition_id).spec
    config_model, task_models = agents.stored_document(db, cfg)
    config = config_model.model_dump(mode="json")
    tasks = [t.model_dump(mode="json") for t in task_models]
    ensure_library(db, run.organization_id, inst.definition_key)
    scenarios = list(db.scalars(select(SimulationScenario).where(
        SimulationScenario.organization_id == run.organization_id, SimulationScenario.agent_key == inst.definition_key,
        SimulationScenario.is_active.is_(True)).order_by(SimulationScenario.key)))
    run.suite = [{"scenario_id": str(s.id), "key": s.key, "version": s.version, "required": s.required}
                 for s in scenarios]
    db.commit()
    caller = gateway.Caller(run.organization_id, run.created_by_id, inst.id)
    rules = _thresholds(db, run.organization_id, inst.definition_key)
    graded_all, mandatory_failures, planner = [], 0, {}
    for s in scenarios:
        r = runtime.run(db, caller, s, spec, config, tasks, rules)
        planner = r["planner"]
        graded = evaluation.grade(s.assertions, r)
        mandatory = any(a["mandatory"] and not a["passed"] for a in graded)
        mandatory_failures += sum(1 for a in graded if a["mandatory"] and not a["passed"])
        analysis = evaluation.analyse({"title": s.title, "doc_type": s.input.get("doc_type"),
                                       "escalation_hint": s.input.get("escalation_hint")}, graded, r, config,
                                      r["task"])
        db.add(SimulationResult(organization_id=run.organization_id, run_id=run.id, scenario_id=s.id,
                                scenario_key=s.key, scenario_version=s.version, category=s.category, title=s.title,
                                passed=all(a["passed"] for a in graded), mandatory_failed=mandatory,
                                outcome=r["outcome"], trace=r["trace"], output=r["output"], assertions=graded,
                                analysis=analysis))
        graded_all.append(graded)
        jobs.step(db, job, "scenario", key=s.key)
    scores = evaluation.scores(graded_all)
    reasons = evaluation.gate(scores, run.thresholds, mandatory_failures, [])
    run.scores, run.planner, run.passed = scores, planner, not reasons
    run.summary = {"scenarios": len(scenarios), "passed": sum(all(a["passed"] for a in g) for g in graded_all),
                   "mandatory_failures": mandatory_failures, "gate_reasons": reasons}
    run.status, run.finished_at = "completed", datetime.now(UTC)
    if run.passed and inst.status == "testing" and inst.current_config_id == run.configuration_id \
            and inst.approved_config_id == run.configuration_id:
        lifecycle.transition(inst, "ready_for_deployment", "Passed the readiness suite")
    audit.record(db, "simulations.completed", actor_type="system", org_id=run.organization_id,
                 target_type="simulation_run", target_id=run.id,
                 data={"passed": run.passed, "mandatory_failures": mandatory_failures,
                       "agent": inst.definition_key, "status_after": inst.status})
    db.commit()


def get_run(db: Session, ctx: OrgContext, run_id: uuid.UUID) -> SimulationRun:
    run = db.get(SimulationRun, run_id)
    if run is None or run.organization_id != ctx.org_id:
        raise not_found("Run")
    return run


def results(db: Session, run: SimulationRun) -> list[SimulationResult]:
    return list(db.scalars(select(SimulationResult).where(SimulationResult.run_id == run.id)
                           .order_by(SimulationResult.passed, SimulationResult.category)))


def runs_for(db: Session, org_id: uuid.UUID, instance_id: uuid.UUID | None = None, limit: int = 50,
             ) -> list[SimulationRun]:
    stmt = select(SimulationRun).where(SimulationRun.organization_id == org_id)
    if instance_id:
        stmt = stmt.where(SimulationRun.instance_id == instance_id)
    return list(db.scalars(stmt.order_by(SimulationRun.created_at.desc()).limit(limit)))


# ---- readiness gate ----------------------------------------------------------------------------------------------

def readiness(db: Session, inst: AgentInstance) -> dict:
    cfg = agents.current_config(db, inst)
    items = []

    def item(key: str, label: str, ok: bool, detail: str) -> None:
        items.append({"key": key, "label": label, "ok": ok, "detail": detail})

    approved = cfg is not None and cfg.status == "approved" and inst.approved_config_id == cfg.id
    item("approved", "Configuration approved by the CEO", approved,
         f"Version {cfg.version} is {cfg.status}" if cfg else "No configuration yet")
    run = None
    if cfg is not None:
        run = db.scalar(select(SimulationRun).where(SimulationRun.instance_id == inst.id,
                                                    SimulationRun.configuration_id == cfg.id,
                                                    SimulationRun.status == "completed")
                        .order_by(SimulationRun.created_at.desc()))
    item("tested", "Readiness suite run on this exact configuration", run is not None and
         run.config_hash == cfg.config_hash == agents.recompute_hash(db, cfg),
         f"Run of {run.finished_at:%Y-%m-%d %H:%M} UTC" if run else "Not run yet for this version")
    item("passed", "All mandatory security checks and thresholds passed", bool(run and run.passed),
         "; ".join(run.summary.get("gate_reasons", [])) or "Passed" if run else "—")
    current_policy = rules_service.policy_version(db, inst.organization_id)
    item("policy", "No business-rule change since the run", bool(run and run.policy_version == current_policy),
         "Confirmed rules changed since the run — re-run the suite" if run and run.policy_version != current_policy
         else "Up to date" if run else "—")
    required = {s.key: s.version for s in db.scalars(select(SimulationScenario).where(
        SimulationScenario.organization_id == inst.organization_id,
        SimulationScenario.agent_key == inst.definition_key, SimulationScenario.is_active.is_(True),
        SimulationScenario.required.is_(True)))}
    covered = {(x["key"], x["version"]) for x in (run.suite if run else [])}
    missing = sorted(k for k, v in required.items() if (k, v) not in covered)
    item("coverage", "Every required scenario included", bool(run) and not missing,
         f"Not covered: {', '.join(missing)}" if missing else "All required scenarios ran" if run else "—")
    return {"ready": all(i["ok"] for i in items), "items": items, "run_id": str(run.id) if run else None,
            "config_hash": cfg.config_hash if cfg else None, "status": inst.status,
            "deployment_stage": inst.deployment_stage}


def needs_retest(db: Session, org_id: uuid.UUID) -> list[dict]:
    """SPEC §4: after a material change (new configuration version, confirmed rules changed, scenario suite updated)
    identify the affected agents. An agent that had been tested (ready/active/paused) and no longer passes the
    readiness gate is listed with the reasons; it keeps its approved configuration but can't be resumed or widened
    until it is re-tested. Bounded by the catalog: one live instance per agent definition."""
    out = []
    for inst in db.scalars(select(AgentInstance).where(AgentInstance.organization_id == org_id,
                                                       AgentInstance.status.in_(("ready", "active", "paused")))
                           .order_by(AgentInstance.definition_key)):
        gate = readiness(db, inst)
        if not gate["ready"]:
            out.append({"instance_id": str(inst.id), "agent": inst.name, "status": inst.status,
                        "reasons": [f"{i['label']}: {i['detail']}" for i in gate["items"] if not i["ok"]]})
    return out


def _require_ready(db: Session, inst: AgentInstance, reviewed_hash: str) -> dict:
    gate = readiness(db, inst)
    if not gate["ready"]:
        raise AppError(409, "not_ready", "The agent hasn't passed the readiness gate",
                       [i for i in gate["items"] if not i["ok"]])
    if reviewed_hash != gate["config_hash"]:
        raise AppError(409, "config_changed", "The configuration changed since you reviewed it")
    return gate


def _record(db: Session, ctx: OrgContext, inst: AgentInstance, subject: str, scope: dict, note: str | None) -> Approval:
    cfg = agents.current_config(db, inst)
    config, tasks = agents.stored_document(db, cfg)
    approval = Approval(organization_id=ctx.org_id, subject_type=subject, subject_id=cfg.id, instance_id=inst.id,
                        subject_version=cfg.version, subject_hash=cfg.config_hash,
                        policy_version=rules_service.policy_version(db, ctx.org_id), decision="approved", note=note,
                        scope={**scope, "configuration": scope_of(cfg.config, tasks)}, decided_by_id=ctx.user.id,
                        decided_by_role=ctx.role)
    db.add(approval)
    return approval


def activate(db: Session, ctx: OrgContext, inst: AgentInstance, reviewed_hash: str, note: str | None) -> AgentInstance:
    gate = _require_ready(db, inst, reviewed_hash)
    lifecycle.transition(inst, "active", "Activated in observation stage")
    # DB clock, like simulation_runs.created_at: `widen` compares the two, and host and DB clocks can differ.
    inst.deployment_stage, inst.activated_at = "observation", func.now()
    _record(db, ctx, inst, "activation", {"stage": "observation", "run_id": gate["run_id"]}, note)
    audit.record(db, "agents.activated", actor_id=ctx.user.id, org_id=ctx.org_id, target_type="agent_instance",
                 target_id=inst.id, data={"stage": "observation", "run_id": gate["run_id"]}, ip=ctx.meta.ip)
    db.commit()
    db.refresh(inst)
    return inst


def widen(db: Session, ctx: OrgContext, inst: AgentInstance, reviewed_hash: str, note: str | None) -> AgentInstance:
    if inst.status != "active" or inst.deployment_stage != "observation":
        raise AppError(409, "invalid_transition", "Only an active agent in observation can be widened")
    gate = _require_ready(db, inst, reviewed_hash)
    run = db.get(SimulationRun, uuid.UUID(gate["run_id"]))
    if run.created_at < inst.activated_at:
        raise AppError(409, "revalidation_required",
                       "Run the readiness suite again after the observation period before widening permissions")
    inst.deployment_stage = "full"
    _record(db, ctx, inst, "deployment_stage", {"stage": "full", "run_id": gate["run_id"]}, note)
    audit.record(db, "agents.stage_widened", actor_id=ctx.user.id, org_id=ctx.org_id, target_type="agent_instance",
                 target_id=inst.id, data={"stage": "full", "run_id": gate["run_id"]}, ip=ctx.meta.ip)
    db.commit()
    db.refresh(inst)
    return inst


def pause(db: Session, ctx: OrgContext, inst: AgentInstance, reason: str | None) -> AgentInstance:
    lifecycle.transition(inst, "paused", reason or "Paused by the CEO")
    audit.record(db, "agents.paused", actor_id=ctx.user.id, org_id=ctx.org_id, target_type="agent_instance",
                 target_id=inst.id, data={"reason": reason}, ip=ctx.meta.ip)
    db.commit()
    db.refresh(inst)
    return inst


def resume(db: Session, ctx: OrgContext, inst: AgentInstance, reviewed_hash: str) -> AgentInstance:
    if inst.status != "paused":
        raise AppError(409, "invalid_transition", "Only a paused agent can be resumed")
    _require_ready(db, inst, reviewed_hash)  # a material change since the last run needs regression testing first
    lifecycle.transition(inst, "active", "Resumed by the CEO")
    audit.record(db, "agents.resumed", actor_id=ctx.user.id, org_id=ctx.org_id, target_type="agent_instance",
                 target_id=inst.id, ip=ctx.meta.ip)
    db.commit()
    db.refresh(inst)
    return inst


# ---- refinement: rollback & suggestions ---------------------------------------------------------------------------

def rollback(db: Session, ctx: OrgContext, inst: AgentInstance, version: int) -> AgentConfiguration:
    """Start a new draft from a previously approved version (it needs approval and testing again)."""
    target = agents.get_version(db, inst, version)
    was_approved = db.scalar(select(Approval.id).where(Approval.subject_type == "agent_configuration",
                                                       Approval.subject_id == target.id,
                                                       Approval.decision == "approved"))
    if not was_approved:
        raise AppError(409, "not_approved", "Only previously approved versions can be restored")
    config, tasks = agents.stored_document(db, target)
    cfg = agents.save_draft(db, ctx, inst, agent_schemas.DraftIn(config=config, tasks=tasks))
    cfg.source = "rollback"
    cfg.generation = {**(target.generation or {}), "rolled_back_from": version}
    audit.record(db, "agents.config_rolled_back", actor_id=ctx.user.id, org_id=ctx.org_id,
                 target_type="agent_configuration", target_id=cfg.id, data={"from_version": version,
                                                                              "new_version": cfg.version},
                 ip=ctx.meta.ip)
    db.commit()
    return cfg


def apply_suggestion(db: Session, ctx: OrgContext, result_id: uuid.UUID, index: int) -> AgentConfiguration:
    result = db.get(SimulationResult, result_id)
    if result is None or result.organization_id != ctx.org_id:
        raise not_found("Result")
    run = db.get(SimulationRun, result.run_id)
    inst = db.get(AgentInstance, run.instance_id)
    suggestions = result.analysis.get("suggestions", [])
    if not 0 <= index < len(suggestions) or not suggestions[index].get("applicable"):
        raise AppError(422, "not_applicable", "This suggestion must be applied by editing the configuration")
    if inst.current_config_id != run.configuration_id:
        raise conflict("The configuration has changed since this run; re-run the suite first")
    s = suggestions[index]
    config_model, tasks = agents.stored_document(db, agents.current_config(db, inst))
    config = copy.deepcopy(config_model.model_dump(mode="json"))
    task_dicts = [t.model_dump(mode="json") for t in tasks]
    if s["kind"] == "permission":
        current = config["permissions"][s["scope"]]
        if policy.MODE_ORDER[s["to"]] >= policy.MODE_ORDER[current]:  # never widen on a test's suggestion
            raise AppError(422, "not_applicable", "Suggestions can only narrow permissions")
        config["permissions"][s["scope"]] = s["to"]
        if s["to"] == "denied":
            spec = db.get(AgentDefinition, inst.definition_id).spec
            needs = {t["key"] for t in spec["tools"] if t["scope"] == s["scope"]}
            config["job"]["authorized_tools"] = [k for k in config["job"]["authorized_tools"] if k not in needs]
            for t in task_dicts:
                t["required_permissions"] = [p for p in t["required_permissions"] if p != s["scope"]]
        else:
            for t in task_dicts:
                if s["scope"] in t["required_permissions"]:
                    t["approval_required"] = True
                    t["approval_reason"] = t["approval_reason"] or "Uses a permission that needs a person's approval."
    elif s["kind"] == "task_approval":
        for t in task_dicts:
            if t["key"] == s["task"]:
                t["approval_required"] = True
                t["approval_reason"] = t["approval_reason"] or "Required after readiness testing."
    elif s["kind"] == "escalation":
        config["job"]["escalation_policies"] = list(dict.fromkeys([*config["job"]["escalation_policies"],
                                                                   s["line"][:300]]))[:25]
    elif s["kind"] == "retries":
        for t in task_dicts:
            if t["key"] == s["task"]:
                t["failure"]["max_retries"] = max(t["failure"]["max_retries"], int(s["to"]))
    else:
        raise AppError(422, "not_applicable", "This suggestion must be applied by editing the configuration")
    cfg = agents.save_draft(db, ctx, inst, agent_schemas.DraftIn.model_validate({"config": config,
                                                                                 "tasks": task_dicts}))
    audit.record(db, "simulations.suggestion_applied", actor_id=ctx.user.id, org_id=ctx.org_id,
                 target_type="agent_configuration", target_id=cfg.id,
                 data={"result_id": str(result.id), "suggestion": s["kind"], "version": cfg.version}, ip=ctx.meta.ip)
    db.commit()
    return cfg

