"""The orchestrator: planner → dispatcher → tool → validator, one step at a time (SPEC §3 step 7, ADR-027).

A run executes in a background job. Each step:
1. the planner proposes one action (a tool call or "finish") from what has been observed so far;
2. the call is validated against the tool's schema, the agent is re-checked with `execution_allowed`, and the
   governance dispatcher (the one the simulation uses) decides executed / blocked / held for approval;
3. a held call raises an action request bound to its exact parameters and the run waits; an approved, unchanged
   action runs once; a rejected one is recorded as rejected;
4. side effects carry an idempotency key unique per workspace, so a retried job or a re-delivered trigger never repeats
   them; idempotent tools are retried on transient faults within the tool's and the task's retry limits;
5. every attempt — whatever happened — is a write-once `tool_executions` row (the evidence).
On "finish", the validator checks completion criteria and that every figure in the summary came from a tool result,
and sets the final status. Delegation is one level deep (the Executive agent asks others; delegated runs can't
delegate), so there is no recursive agent-to-agent conversation.
"""

import hashlib
import json
import re
import uuid
from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from abos.agents import service as agents
from abos.agents.models import AgentConfiguration, AgentDefinition, AgentInstance
from abos.audit import service as audit
from abos.company import service as company
from abos.core.errors import AppError, conflict, not_found
from abos.core.logging import log_context
from abos.governance import actions, dispatch
from abos.governance import rules as rules_service
from abos.governance.models import ActionRequest
from abos.identity.deps import OrgContext
from abos.jobs import service as jobs
from abos.knowledge.models import JobRun
from abos.llm import gateway
from abos.notifications import service as notifications
from abos.orchestration import planner, state
from abos.orchestration.models import WorkflowRun
from abos.orchestration.runs import JOB_KIND, new_run, requeue
from abos.tools import handlers, registry
from abos.tools.models import ToolExecution
from abos.usage import service as usage

GUARD_STOP = "guard"
_NUM = re.compile(r"\d+(?:[.,]\d+)*")


def _now() -> datetime:
    return datetime.now(UTC)


def _canonical(data) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)


# ---- starting runs -----------------------------------------------------------------------------------------------

def start(db: Session, ctx: OrgContext, inst: AgentInstance, *, task_key: str | None, request: str | None,
          idempotency_key: str | None) -> WorkflowRun:
    """A person runs a task now, or asks the agent something (task 'request')."""
    ok, reason = agents.execution_allowed(db, inst)
    if not ok:
        raise AppError(409, "not_allowed", reason)
    if task_key and task_key != "request":
        cfg = db.get(AgentConfiguration, inst.approved_config_id)
        task = next((t for t in agents.task_rows(db, cfg) if t.key == task_key), None)
        if task is None:
            raise not_found("Task")
        title = task.title
    else:
        if not (request or "").strip():
            raise AppError(422, "validation_error", "Say what you need")
        task_key, title = "request", f"Request: {request.strip()[:180]}"
    key = f"manual:{ctx.user.id}:{idempotency_key}" if idempotency_key else f"manual:{uuid.uuid4()}"
    run = new_run(db, inst, task_key=task_key, task_title=title, trigger_type="on_demand",
                  trigger={"requested_by": str(ctx.user.id)}, idempotency_key=key,
                  request=request.strip() if task_key == "request" else None, requested_by_id=ctx.user.id)
    if run is None:  # the same request key was already used: return that run instead of starting another
        existing = db.scalar(select(WorkflowRun).where(WorkflowRun.organization_id == ctx.org_id,
                                                       WorkflowRun.idempotency_key == key))
        if existing is None:
            raise conflict("This agent has no approved configuration")
        return existing
    audit.record(db, "workflows.requested", actor_id=ctx.user.id, org_id=ctx.org_id, target_type="workflow_run",
                 target_id=run.id, data={"agent": inst.definition_key, "task": task_key}, ip=ctx.meta.ip)
    db.commit()
    db.refresh(run)
    return run


def cancel(db: Session, ctx: OrgContext, run: WorkflowRun) -> WorkflowRun:
    if run.status not in ("queued", "awaiting_approval", "waiting_children"):
        raise AppError(409, "invalid_transition", f"A {state.LABELS[run.status].lower()} run can't be cancelled")
    state.transition(run, "cancelled", f"Cancelled by {ctx.user.full_name}")
    run.finished_at = _now()
    for req in db.scalars(select(ActionRequest).where(ActionRequest.run_id == run.id,
                                                      ActionRequest.status == "pending")):
        req.status = "cancelled"
    for child in db.scalars(select(WorkflowRun).where(WorkflowRun.parent_id == run.id,
                                                      WorkflowRun.status.in_(("queued", "awaiting_approval")))):
        state.transition(child, "cancelled", "The requesting run was cancelled")
        child.finished_at = _now()
    audit.record(db, "workflows.cancelled", actor_id=ctx.user.id, org_id=ctx.org_id, target_type="workflow_run",
                 target_id=run.id, ip=ctx.meta.ip)
    db.commit()
    return run


def resume_after_decision(db: Session, req: ActionRequest) -> None:
    """A held action was decided: the waiting run continues (the caller commits; the job starts after commit)."""
    run = db.scalar(select(WorkflowRun).where(WorkflowRun.id == req.run_id).with_for_update())
    if run is not None and run.status == "awaiting_approval":
        state.transition(run, "queued", "Approval decision recorded")
        requeue(db, run)


# ---- the job -----------------------------------------------------------------------------------------------------

@jobs.handler(JOB_KIND)
def execute(db: Session, job: JobRun) -> None:
    try:
        with log_context(run_id=job.target_id):
            advance(db, job.target_id, retry=job.attempts > 1)
    except Exception as exc:
        if job.attempts >= job.max_attempts:
            db.rollback()
            _fail(db, job.target_id, f"The run errored: {type(exc).__name__}")
        raise


def _fail(db: Session, run_id: uuid.UUID, reason: str) -> None:
    run = db.get(WorkflowRun, run_id)
    if run is not None and run.status not in state.TERMINAL:
        run.status, run.status_reason, run.error, run.finished_at = "failed", reason, reason, _now()
        db.commit()
        _on_finished(db, run)


def advance(db: Session, run_id: uuid.UUID, *, retry: bool = False) -> None:
    run = db.scalar(select(WorkflowRun).where(WorkflowRun.id == run_id).with_for_update())
    if run is None or run.status not in ("queued", "running") or (run.status == "running" and not retry):
        db.rollback()
        return
    # Lock the agent row: claims for one agent are serialised, so overlap and daily-limit checks can't race.
    inst = db.scalar(select(AgentInstance).where(AgentInstance.id == run.instance_id).with_for_update())
    if run.status == "queued":
        if run.not_before and run.not_before > _now():
            db.rollback()
            return  # deferred to business hours; the scheduler queues it when the window opens
        if reason := _claim_refusal(db, run, inst):
            kind, why = reason
            state.transition(run, kind, why)
            run.finished_at = _now()
            db.commit()
            _on_finished(db, run)
            return
        state.transition(run, "running", None)
        run.started_at = run.started_at or _now()
    run.heartbeat_at = _now()
    db.commit()
    _loop(db, run, inst)


def _claim_refusal(db: Session, run: WorkflowRun, inst: AgentInstance) -> tuple[str, str] | None:
    ok, why = agents.execution_allowed(db, inst)
    if not ok:
        return "blocked", why
    if inst.approved_config_id != run.configuration_id:
        return "blocked", "The approved configuration changed after this run was created"
    if db.scalar(select(WorkflowRun.id).where(WorkflowRun.lock_key == run.lock_key, WorkflowRun.status == "running",
                                              WorkflowRun.id != run.id)):
        return "skipped", "Another run of this task is still in progress"
    cfg = db.get(AgentConfiguration, run.configuration_id)
    limit = cfg.config["limits"]["max_runs_per_day"]
    tz = company.get_profile(db, run.organization_id).timezone
    midnight = datetime.combine(_now().astimezone(ZoneInfo(tz) if tz else UTC).date(), time(0),
                                ZoneInfo(tz) if tz else UTC)
    started = db.scalar(select(func.count()).select_from(WorkflowRun).where(
        WorkflowRun.instance_id == inst.id, WorkflowRun.started_at >= midnight, WorkflowRun.depth == run.depth)) or 0
    if started >= limit:
        return "skipped", f"Daily run limit reached ({limit} runs)"
    budget = usage.agent_budget(db, inst)
    if budget["over"]:
        notifications.notify(db, run.organization_id, kind="budget", severity="warning",
                             title=f"{inst.name} reached its monthly AI budget",
                             body=f"Spent {budget['spent_usd']} of {budget['budget_usd']} USD this month; runs are "
                                  "skipped until the budget is raised or the month ends.",
                             link="/app/usage", subject_type="agent_instance", subject_id=inst.id,
                             dedupe=f"budget:{inst.id}:{usage.month_start(db, inst.organization_id).date()}")
        return "skipped", f"Monthly AI budget reached ({budget['spent_usd']} of {budget['budget_usd']} USD)"
    return None


# ---- the loop ----------------------------------------------------------------------------------------------------

class _Run:
    """Everything a step needs, loaded once per job."""

    def __init__(self, db: Session, run: WorkflowRun, inst: AgentInstance):
        self.cfg = db.get(AgentConfiguration, run.configuration_id)
        self.spec = db.get(AgentDefinition, inst.definition_id).spec
        config, tasks = agents.stored_document(db, self.cfg)
        self.config = config.model_dump(mode="json")
        self.task = next((t.model_dump(mode="json") for t in tasks if t.key == run.task_key), None)
        self.tools = registry.tools_for(self.spec)
        self.thresholds = rules_service.money_thresholds(db, run.organization_id, inst.definition_key)
        self.caller = gateway.Caller(run.organization_id, run.requested_by_id, inst.id)


def _loop(db: Session, run: WorkflowRun, inst: AgentInstance) -> None:
    r = _Run(db, run, inst)
    for x in _ledger(db, run.id):  # a worker died mid-call: the outcome is unknown and the call is not repeated
        if x.status == "started":
            x.status, x.finished_at = "unverified", _now()
            x.reason = "The previous attempt stopped before its outcome was recorded; not repeated"
    db.commit()
    for _ in range(planner.MAX_STEPS + 1):
        rows = _ledger(db, run.id)
        held = rows[-1] if rows and rows[-1].status == "held" else None
        if len({x.step_no for x in rows}) >= planner.MAX_STEPS and held is None:
            _finish(db, run, inst, r, planner.finish("The run stopped at the step limit.",
                                                     missing=[f"Stopped after {planner.MAX_STEPS} steps"]),
                    forced="failed")
            return
        ctx = _plan_context(db, run, inst, r, rows)
        if held is not None:  # a decided (or still pending) held action: dispatch the same call at the same step
            action, step_no, mode = planner.call(held.tool, held.input), held.step_no, held.planner
        else:
            action, result = planner.next_action(r.caller, ctx)
            mode = "playbook" if result.is_dev else "model"
            run.planner = {"mode": mode, "provider": result.provider, "model": result.model,
                           "label": ("Playbook — no AI model planned these steps; a deterministic plan for this "
                                     "task proposed each call and every call went through governance.")
                           if result.is_dev else None}
            step_no = (max((x.step_no for x in rows), default=0)) + 1
        if action.get("action") == "finish":
            _finish(db, run, inst, r, action, ctx=ctx)
            return
        row, stop = _call(db, run, inst, r, step_no, str(action.get("tool", "")), action.get("input"), mode)
        run.steps = [*run.steps, {"n": step_no, "tool": row.tool, "status": row.status, "decision": row.decision,
                                  "reason": row.reason, "execution_id": str(row.id),
                                  "note": str(action.get("note", ""))[:200]}]
        run.heartbeat_at = _now()
        if stop == GUARD_STOP:
            state.transition(run, "blocked", row.reason)
            run.finished_at = _now()
            db.commit()
            _on_finished(db, run)
            return
        if row.status == "held":
            state.transition(run, "awaiting_approval", row.reason)
            db.commit()
            return
        if row.tool == "agents.delegate" and row.status == "succeeded" and _children_pending(db, run):
            state.transition(run, "waiting_children", "Waiting for the delegated agents")
            db.commit()  # children start after this commit
            return
        db.commit()
        db.refresh(run)
        if run.status != "running":  # cancelled, or finished by a nested inline job (eager mode)
            return
    _finish(db, run, inst, r, planner.finish("The run stopped at the step limit."), forced="failed")


def _ledger(db: Session, run_id: uuid.UUID) -> list[ToolExecution]:
    return list(db.scalars(select(ToolExecution).where(ToolExecution.run_id == run_id)
                           .order_by(ToolExecution.step_no, ToolExecution.created_at)))


def _plan_context(db: Session, run: WorkflowRun, inst: AgentInstance, r: _Run,
                  rows: list[ToolExecution]) -> planner.PlanContext:
    obs = [planner.Obs(x.step_no, x.tool, x.input, x.status, x.output or {}, x.reason) for x in rows]
    return planner.PlanContext(
        agent_key=inst.definition_key, agent_name=inst.name, config=r.config, task=r.task, task_key=run.task_key,
        request=run.request, tools=r.tools, observations=obs, today=_today(db, run.organization_id),
        trigger=run.trigger or {}, children=_children(db, run), can_delegate=run.depth == 0 and
        "agents.delegate" in r.tools, limit_currencies={t.currency for t in r.thresholds})


def _today(db: Session, org_id: uuid.UUID):
    from abos.business.service import company_today  # noqa: PLC0415

    return company_today(db, org_id)


# ---- one call through governance -----------------------------------------------------------------------------------

def _record(db: Session, run: WorkflowRun, inst: AgentInstance, *, step_no: int, tool: str, tdef, data,
            decision: str, reason: str, status: str, mode: str, started: datetime, **kw) -> ToolExecution:
    row = ToolExecution(organization_id=run.organization_id, run_id=run.id, instance_id=inst.id, step_no=step_no,
                        tool=tool[:60], registry_version=registry.REGISTRY_VERSION,
                        scope=tdef.scope if tdef else None, risk=tdef.risk if tdef else "high",
                        input=data if isinstance(data, dict | list | str | int | float | bool) else str(data),
                        input_hash=hashlib.sha256(_canonical(data).encode()).hexdigest(), decision=decision,
                        reason=reason[:500], status=status, planner=mode, started_at=started,
                        finished_at=kw.pop("finished_at", _now()), **kw)
    if row.finished_at:
        row.duration_ms = int((row.finished_at - started).total_seconds() * 1000)
    db.add(row)
    db.flush()
    if tdef is not None and tdef.audit == "ledger+audit" and status in ("succeeded", "unverified"):
        audit.record(db, f"tools.{tool}", actor_type="agent", org_id=run.organization_id,
                     target_type="tool_execution", target_id=row.id,
                     data={"agent": inst.definition_key, "run_id": str(run.id), "status": status})
    return row


def _call(db: Session, run: WorkflowRun, inst: AgentInstance, r: _Run, step_no: int, name: str, data,
          mode: str) -> tuple[ToolExecution, str | None]:
    started = _now()
    base = {"step_no": step_no, "tool": name, "data": data, "mode": mode, "started": started}
    tdef = r.tools.get(name)
    if tdef is None:
        return _record(db, run, inst, tdef=None, decision="rejected", reason=f"Unknown tool \"{name[:60]}\"",
                       status="unknown_tool", **base), None
    validated, problem = registry.validate(tdef, data)
    if problem:
        return _record(db, run, inst, tdef=tdef, decision="rejected_input", reason=problem, status="rejected_input",
                       **base), None
    ok, why = agents.execution_allowed(db, inst)
    if not ok:
        return _record(db, run, inst, tdef=tdef, decision="blocked", reason=why, status="blocked", **base), GUARD_STOP
    clean = validated.model_dump(mode="json", exclude_none=True)
    decision, reason = dispatch.decide(tool=name, label=tdef.label, scope=tdef.scope, platform=tdef.platform,
                                       data=clean, config=r.config, stage=inst.deployment_stage, task=r.task,
                                       thresholds=r.thresholds)
    if decision == "executed" and tdef.approval == "always":
        decision, reason = "held_for_approval", f"Every use of \"{tdef.label}\" needs a person's approval"
    if decision == "blocked":
        return _record(db, run, inst, tdef=tdef, decision=decision, reason=reason, status="blocked", **base), None
    if tdef.unavailable:
        return _record(db, run, inst, tdef=tdef, decision=decision, reason=tdef.unavailable, status="unavailable",
                       **base), None
    tctx = handlers.ToolContext(db, run.organization_id, inst, run, r.config, r.caller, r.thresholds)
    approved = None
    if decision == "held_for_approval":
        try:
            parameters = tdef.parameters(tctx, validated) if tdef.parameters else clean
        except handlers.Refused as exc:
            return _record(db, run, inst, tdef=tdef, decision=decision, reason=str(exc), status="refused",
                           **base), None
        policy = rules_service.policy_version(db, run.organization_id)
        digest = actions.params_hash(tool=name, parameters=parameters, instance_id=inst.id,
                                     config_hash=r.cfg.config_hash, policy_version=policy)
        if rejected := actions.rejected_for(db, run.id, step_no, digest):
            return _record(db, run, inst, tdef=tdef, decision=decision, status="rejected",
                           reason=f"Rejected by the approver: {rejected.note or ''}"[:500],
                           approval_request_id=rejected.id, **base), None
        approved = actions.approved_for(db, run.id, step_no, digest)
        if approved is None:
            changed = any(x.status == "approved" for x in actions.for_step(db, run.id, step_no))
            req = actions.raise_request(db, run, step_no=step_no, tool=tdef, data=clean, parameters=parameters,
                                        digest=digest, policy_version=policy,
                                        reason=("The action changed after it was approved; it needs a new approval. "
                                                if changed else "") + reason)
            return _record(db, run, inst, tdef=tdef, decision=decision, reason=req.reason, status="held",
                           approval_request_id=req.id, **base), None
        approved.status = "used"
        reason = f"Approved by a person (request {approved.id})"
    return _execute(db, run, inst, r, tdef, validated, clean, tctx, base, decision, reason, approved)


def _execute(db, run, inst, r, tdef, validated, clean, tctx, base, decision, reason, approved):
    approval_id = approved.id if approved else None
    key = None
    if tdef.side_effect:
        key = hashlib.sha256(f"{inst.id}|{tdef.key}|{_canonical(clean)}|{run.idempotency_key}".encode()).hexdigest()
        prior = db.scalar(select(ToolExecution).where(ToolExecution.organization_id == run.organization_id,
                                                      ToolExecution.idempotency_key == key))
        if prior is not None:
            if prior.status == "started":  # a previous attempt crashed mid-call: its outcome is unknown
                prior.status, prior.finished_at = "unverified", _now()
                prior.reason = "The previous attempt stopped before its outcome was recorded; not repeated"
                db.flush()
                return prior, None
            if prior.status != "succeeded":  # repeating isn't safe and the first outcome isn't known
                return _record(db, run, inst, tdef=tdef, decision="duplicate", status="unverified",
                               reason=f"Already attempted for this trigger (execution {prior.id}); its outcome is "
                                      "unknown, so it is not repeated", **base), None
            return _record(db, run, inst, tdef=tdef, decision="duplicate", status="duplicate",
                           reason=f"Already performed for this trigger (execution {prior.id})",
                           output=prior.output, evidence=prior.evidence, **base), None
    ok, why = agents.execution_allowed(db, inst, tdef.scope, approved_action=approved is not None)
    if not ok:
        return _record(db, run, inst, tdef=tdef, decision="blocked", reason=why, status="blocked", **base), \
            GUARD_STOP
    started_row = None
    if tdef.side_effect and not tdef.transactional:  # record intent first: a crash leaves evidence, not a mystery
        started_row = _record(db, run, inst, tdef=tdef, decision=decision, reason=reason, status="started",
                              idempotency_key=key, approval_request_id=approval_id, finished_at=None, **base)
        db.commit()
        key = None
    retries = (r.task or {}).get("failure", {}).get("max_retries", 2)
    max_attempts = min(tdef.max_attempts, retries + 1) if tdef.idempotent else 1
    attempts, status, output, evidence, error = 0, "failed", {}, [], None
    handler = tdef.handler or SPECIAL[tdef.key]
    while attempts < max(1, max_attempts):
        attempts += 1
        sp = db.begin_nested()
        try:
            db.execute(text(f"SET LOCAL statement_timeout = {int(tdef.timeout_seconds * 1000)}"))
            result = handler(tctx, validated)
            sp.commit()
        except handlers.Refused as exc:
            sp.rollback()
            return _finish_row(db, started_row, run, inst, tdef, base, decision, str(exc), "refused", attempts,
                               key=key, approval_id=approval_id), None
        except (handlers.Transient, DBAPIError) as exc:
            sp.rollback()
            error = f"{type(exc).__name__}: {str(exc).splitlines()[0][:200]}"
            transient = isinstance(exc, handlers.Transient) or getattr(getattr(exc, "orig", None), "sqlstate",
                                                                       "") in ("57014", "08006", "08001")
            if transient and attempts < max_attempts:
                continue
            status = "unverified" if not tdef.transactional and tdef.side_effect else "failed"
            reason = (f"Timed out after {attempts} attempt(s)" if transient else "The tool errored") + \
                ("; the outcome is unknown" if status == "unverified" else "")
            break
        except Exception as exc:  # noqa: BLE001 — every failure is evidence, the run decides what follows
            sp.rollback()
            error = f"{type(exc).__name__}: {str(exc)[:200]}"
            status = "unverified" if not tdef.transactional and tdef.side_effect else "failed"
            reason = "The tool errored" + ("; the outcome is unknown" if status == "unverified" else "")
            break
        else:
            status, output, evidence = result.status, result.output, result.evidence
            break
    return _finish_row(db, started_row, run, inst, tdef, base, decision, reason, status, attempts, output=output,
                       evidence=evidence, error=error, key=key, approval_id=approval_id), None


def _finish_row(db, started_row, run, inst, tdef, base, decision, reason, status, attempts, *, output=None,
                evidence=None, error=None, key=None, approval_id=None) -> ToolExecution:
    if started_row is not None:  # complete the intent row (the one UPDATE the ledger allows)
        started_row.status, started_row.reason, started_row.attempts = status, reason[:500], attempts
        started_row.output, started_row.evidence, started_row.error = output or {}, evidence or [], error
        started_row.finished_at = _now()
        started_row.duration_ms = int((started_row.finished_at - started_row.started_at).total_seconds() * 1000)
        db.flush()
        return started_row
    return _record(db, run, inst, tdef=tdef, decision=decision, reason=reason, status=status, attempts=attempts,
                   output=output or {}, evidence=evidence or [], error=error,
                   idempotency_key=key if status in ("succeeded", "unverified") else None,
                   approval_request_id=approval_id, **base)


# ---- delegation (one level) --------------------------------------------------------------------------------------

def _delegate(tctx: handlers.ToolContext, data) -> handlers.ToolResult:
    run, db = tctx.run, tctx.db
    if run.depth >= 1:
        raise handlers.Refused("Delegated runs can't delegate further")
    others = [i for i in db.scalars(select(AgentInstance).where(
        AgentInstance.organization_id == run.organization_id, AgentInstance.status == "active",
        AgentInstance.id != run.instance_id).order_by(AgentInstance.definition_key))
        if not data.agents or i.definition_key in data.agents][:7]
    children = []
    for o in others:
        key = f"delegate:{run.id}:{o.id}"
        child = new_run(db, o, task_key="request", task_title=f"Request from {tctx.inst.name}",
                        trigger_type="delegated", trigger={"parent_run_id": str(run.id)}, idempotency_key=key,
                        request=data.request, requested_by_id=run.requested_by_id, parent=run) or db.scalar(
            select(WorkflowRun).where(WorkflowRun.organization_id == run.organization_id,
                                      WorkflowRun.idempotency_key == key))
        if child is not None:
            children.append({"run_id": str(child.id), "agent": o.name, "agent_key": o.definition_key})
    return handlers.ToolResult({"children": children, "count": len(children)},
                               [handlers.ref("workflow_run", c["run_id"], c["agent"]) for c in children])


SPECIAL = {"agents.delegate": _delegate}


def _children(db: Session, run: WorkflowRun) -> list[dict]:
    rows = db.execute(select(WorkflowRun, AgentInstance.name).join(AgentInstance, AgentInstance.id ==
                                                                   WorkflowRun.instance_id)
                      .where(WorkflowRun.parent_id == run.id).order_by(WorkflowRun.created_at)).all()
    return [{"run_id": str(c.id), "agent": name, "status": c.status, "reason": c.status_reason,
             "summary": (c.output or {}).get("summary", ""), "findings": (c.output or {}).get("findings", []),
             "missing_evidence": (c.output or {}).get("missing_evidence", [])} for c, name in rows]


def _children_pending(db: Session, run: WorkflowRun) -> bool:
    return bool(db.scalar(select(WorkflowRun.id).where(WorkflowRun.parent_id == run.id,
                                                       WorkflowRun.status.in_(tuple(state.ACTIVE)))))


def _on_finished(db: Session, run: WorkflowRun) -> None:
    """A delegated run finished: when it was the last one, the waiting parent continues."""
    if run.parent_id is None:
        return
    parent = db.scalar(select(WorkflowRun).where(WorkflowRun.id == run.parent_id).with_for_update())
    if parent is not None and parent.status == "waiting_children" and not _children_pending(db, parent):
        state.transition(parent, "queued", "Delegated agents finished")
        requeue(db, parent)
    db.commit()


# ---- validation & finishing --------------------------------------------------------------------------------------

def _numbers(value) -> set[str]:
    return {n.replace(",", "") for n in _NUM.findall(value if isinstance(value, str) else _canonical(value))}


def _norm(n: str) -> str:
    return n.rstrip("0").rstrip(".") if "." in n else n


def validate(ctx: planner.PlanContext, action: dict) -> tuple[str, list[dict]]:
    """(status, checks). Deterministic: no model judges a model."""
    obs = ctx.observations
    final = [o for o in obs if o.status != "held"]
    checks = []

    def check(label: str, ok: bool, detail: str) -> None:
        checks.append({"label": label, "ok": ok, "detail": detail})

    failed = [o for o in final if o.status == "failed"]
    unknown = [o for o in final if o.status in ("unverified", "started")]
    refused = [o for o in final if o.status in ("blocked", "refused", "rejected_input", "unknown_tool")]
    unavailable = [o for o in final if o.status == "unavailable"]
    rejected = [o for o in final if o.status == "rejected"]
    check("Every action finished", not failed, "; ".join(f"step {o.n} {o.tool}: {o.reason}" for o in failed)
          or f"{len(final)} steps")
    check("Every outcome is known", not unknown,
          "; ".join(f"step {o.n} {o.tool}: {o.reason}" for o in unknown) or "No unverified outcomes")
    check("Every attempted action was allowed", not refused,
          "; ".join(f"step {o.n} {o.tool}: {o.reason}" for o in refused) or "Nothing was refused")
    check("Needed integrations are connected", not unavailable,
          "; ".join(sorted({o.tool for o in unavailable})) or "All connected")
    if rejected:
        check("Held actions decided", True, f"{len(rejected)} rejected by the approver")
    pool = set()
    for o in obs:
        pool |= _numbers(o.output) | _numbers(o.input)
        pool |= {str(len(v)) for v in o.output.values() if isinstance(v, list)}
    pool |= _numbers(ctx.children) | _numbers(ctx.request or "") | _numbers(ctx.task or {})
    pool |= {str(len(ctx.children)), str(sum(1 for c in ctx.children if c["status"] == "completed")),
             str(len(ctx.children) - sum(1 for c in ctx.children if c["status"] == "completed"))}
    pool |= {str(sum(1 for o in obs if o.tool == t and o.status == "succeeded")) for t in {o.tool for o in obs}}
    normalised = {_norm(p) for p in pool}
    stated = _numbers(action.get("summary", "")) | _numbers(action.get("findings", []))
    unsupported = sorted(n for n in stated if _norm(n) not in normalised)
    check("Every figure comes from a tool result", not unsupported,
          f"Unsupported: {', '.join(unsupported[:10])}" if unsupported else "All figures traced to tool results")
    for c in action.get("criteria", []):
        check(c["label"], bool(c["ok"]), c.get("detail", ""))
    if failed:
        return "failed", checks
    if unknown or unsupported:
        return "unverified", checks
    if any(not c["ok"] for c in checks) or action.get("missing_evidence"):
        return "needs_review", checks
    return "completed", checks


def _finish(db: Session, run: WorkflowRun, inst: AgentInstance, r: _Run, action: dict, *,
            ctx: planner.PlanContext | None = None, forced: str | None = None) -> None:
    ctx = ctx or _plan_context(db, run, inst, r, _ledger(db, run.id))
    status, checks = validate(ctx, action)
    status = forced or status
    on_failure = (r.task or {}).get("failure", {}).get("on_failure", "escalate")
    if status == "failed" and on_failure == "escalate" and not any(o.tool == "escalate" for o in ctx.observations):
        step_no = max((o.n for o in ctx.observations), default=0) + 1
        row, _ = _call(db, run, inst, r, step_no, "escalate",
                       {"reason": f"Task \"{run.task_title}\" failed: "
                                  + "; ".join(c["detail"] for c in checks if not c["ok"])[:400],
                        "severity": "high", "subject": f"run:{run.id}"}, "playbook")
        run.steps = [*run.steps, {"n": step_no, "tool": "escalate", "status": row.status, "decision": row.decision,
                                  "reason": "Automatic escalation (task failure policy)",
                                  "execution_id": str(row.id), "note": ""}]
    run.output = {"summary": action.get("summary", ""), "findings": action.get("findings", []),
                  "missing_evidence": action.get("missing_evidence", []),
                  "label": (run.planner or {}).get("label")}
    run.validation = {"passed": status == "completed", "checks": checks}
    failing = [c["label"] for c in checks if not c["ok"]]
    state.transition(run, status)
    run.status_reason = "; ".join(failing)[:500] or None
    run.finished_at = _now()
    audit.record(db, f"workflows.{status}", actor_type="agent", org_id=run.organization_id,
                 target_type="workflow_run", target_id=run.id,
                 data={"agent": inst.definition_key, "task": run.task_key, "steps": len(run.steps)})
    if status in ("failed", "unverified"):
        notifications.notify(db, run.organization_id, kind=f"run_{status}",
                             severity="critical" if status == "unverified" else "warning",
                             title=f"{inst.name}: {run.task_title} — "
                                   + ("outcome unknown" if status == "unverified" else "failed"),
                             body=run.status_reason or action.get("summary", ""), link=f"/app/tasks/{run.id}",
                             subject_type="workflow_run", subject_id=run.id, dedupe=f"run:{run.id}:{status}")
    db.commit()
    _on_finished(db, run)


# ---- reading -----------------------------------------------------------------------------------------------------

def get_run(db: Session, ctx: OrgContext, run_id: uuid.UUID) -> WorkflowRun:
    run = db.get(WorkflowRun, run_id)
    if run is None or run.organization_id != ctx.org_id:
        raise not_found("Run")
    return run


def list_runs(db: Session, ctx: OrgContext, *, instance_id: uuid.UUID | None = None, status: str | None = None,
              top_level: bool = False, limit: int = 50) -> list[tuple[WorkflowRun, str, str]]:
    stmt = (select(WorkflowRun, AgentInstance.name, AgentInstance.definition_key)
            .join(AgentInstance, AgentInstance.id == WorkflowRun.instance_id)
            .where(WorkflowRun.organization_id == ctx.org_id))
    if instance_id:
        stmt = stmt.where(WorkflowRun.instance_id == instance_id)
    if status:
        stmt = stmt.where(WorkflowRun.status == status)
    if top_level:
        stmt = stmt.where(WorkflowRun.parent_id.is_(None))
    return [tuple(x) for x in db.execute(stmt.order_by(WorkflowRun.created_at.desc()).limit(limit)).all()]


def executions(db: Session, ctx: OrgContext, *, run_id: uuid.UUID | None = None,
               instance_id: uuid.UUID | None = None, tool: str | None = None, limit: int = 100) -> list[ToolExecution]:
    stmt = select(ToolExecution).where(ToolExecution.organization_id == ctx.org_id)
    if run_id:
        stmt = stmt.where(ToolExecution.run_id == run_id)
    if instance_id:
        stmt = stmt.where(ToolExecution.instance_id == instance_id)
    if tool:
        stmt = stmt.where(ToolExecution.tool == tool)
    order = (ToolExecution.step_no, ToolExecution.created_at) if run_id else (ToolExecution.created_at.desc(),)
    return list(db.scalars(stmt.order_by(*order).limit(limit)))


def detail(db: Session, ctx: OrgContext, run: WorkflowRun) -> dict:
    inst = db.get(AgentInstance, run.instance_id)
    parent = db.get(WorkflowRun, run.parent_id) if run.parent_id else None
    return {"run": run, "agent_name": inst.name, "definition_key": inst.definition_key,
            "executions": executions(db, ctx, run_id=run.id, limit=500),
            "action_requests": [actions.out(db, a) for a in db.scalars(
                select(ActionRequest).where(ActionRequest.run_id == run.id).order_by(ActionRequest.created_at))],
            "children": _children(db, run),
            "parent": {"run_id": str(parent.id), "task_title": parent.task_title} if parent else None}


def runnable_tasks(db: Session, ctx: OrgContext) -> list[dict]:
    """Tasks a person can run now: those of active agents' approved configurations, plus an ad-hoc request."""
    out = []
    for inst in db.scalars(select(AgentInstance).where(AgentInstance.organization_id == ctx.org_id,
                                                       AgentInstance.status != "retired")
                           .order_by(AgentInstance.definition_key)):
        ok, reason = agents.execution_allowed(db, inst)
        cfg = db.get(AgentConfiguration, inst.approved_config_id) if inst.approved_config_id else None
        tasks = [{"key": t.key, "title": t.title, "trigger_type": t.trigger_type, "event": t.event,
                  "schedule": t.schedule, "required_permissions": t.required_permissions}
                 for t in (agents.task_rows(db, cfg) if cfg else [])]
        out.append({"instance_id": inst.id, "agent_name": inst.name, "definition_key": inst.definition_key,
                    "status": inst.status, "deployment_stage": inst.deployment_stage, "can_run": ok,
                    "reason": reason, "tasks": tasks})
    return out
