"""AI workforce service: catalog, hiring, versioned configurations, lifecycle, and the execution guard.

Configuration versions (ADR-018): the current version is editable only while it is a draft. Saving or regenerating
after submission creates the next version and sends the agent back to `configuring`, so the CEO always approves a
frozen document whose hash is recorded with the decision.
"""

import hashlib
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from abos.agents import design, lifecycle, schedule, validation
from abos.agents import schemas as s
from abos.agents.models import AgentConfiguration, AgentDefinition, AgentInstance, TaskDefinition, TaskDependency
from abos.audit import service as audit
from abos.company import service as company
from abos.core.errors import AppError, conflict, not_found
from abos.governance import rules as rules_service
from abos.governance.models import Approval, BusinessRule
from abos.identity.deps import OrgContext
from abos.knowledge.models import InterviewQuestion
from abos.llm import gateway

LIVE_EDIT_STATES = ("selected", "configuring", "awaiting_approval", "testing", "ready_for_deployment", "active",
                    "paused", "failed")


# ---- catalog -----------------------------------------------------------------------------------------------------

def definition_out(d: AgentDefinition, status: str = "available", instance_id: uuid.UUID | None = None,
                   ) -> s.DefinitionOut:
    sp = d.spec
    return s.DefinitionOut(
        id=d.id, key=d.key, version=d.version, letter=d.letter, name=d.name, title=sp["title"],
        department=d.department, expertise=sp["expertise"], role_description=sp["role_description"],
        responsibilities=sp["responsibilities"], prohibited=sp["prohibited"],
        required_knowledge=sp["required_knowledge"], data_sources=sp["data_sources"], tools=sp["tools"],
        permission_ceilings=sp["permission_ceilings"], escalation_conditions=sp["escalation_conditions"],
        kpis=sp["kpis"], reporting_frequency=sp["reporting_frequency"],
        default_operating_mode=sp["default_operating_mode"], default_automation=sp["default_automation"],
        model=sp["model"], default_monthly_budget_usd=Decimal(sp["default_monthly_budget_usd"]),
        supported_events=sp["supported_events"], task_templates=sp["tasks"], status=status, instance_id=instance_id)


def _live(db: Session, org_id: uuid.UUID) -> dict[str, AgentInstance]:
    return {i.definition_key: i for i in db.scalars(select(AgentInstance).where(
        AgentInstance.organization_id == org_id, AgentInstance.status != "retired"))}


def catalog(db: Session, org_id: uuid.UUID) -> list[s.DefinitionOut]:
    live = _live(db, org_id)
    defs = db.scalars(select(AgentDefinition).where(AgentDefinition.is_current.is_(True))
                      .order_by(AgentDefinition.letter))
    return [definition_out(d, live[d.key].status if d.key in live else "available",
                           live[d.key].id if d.key in live else None) for d in defs]


def current_definition(db: Session, key: str) -> AgentDefinition:
    d = db.scalar(select(AgentDefinition).where(AgentDefinition.key == key, AgentDefinition.is_current.is_(True)))
    if d is None:
        raise not_found("Agent definition")
    return d


# ---- instances ---------------------------------------------------------------------------------------------------

def get(db: Session, ctx: OrgContext, instance_id: uuid.UUID) -> AgentInstance:
    inst = db.get(AgentInstance, instance_id)
    if inst is None or inst.organization_id != ctx.org_id:  # same 404 for another tenant's agent
        raise not_found("Agent")
    return inst


def hire(db: Session, ctx: OrgContext, keys: list[str], source: str) -> list[AgentInstance]:
    keys = list(dict.fromkeys(keys))
    definitions = [current_definition(db, k) for k in keys]
    live = _live(db, ctx.org_id)
    taken = [d.name for d in definitions if d.key in live]
    if taken:
        raise conflict(f"Already hired: {', '.join(taken)}")
    created = []
    try:
        for d in definitions:
            inst = AgentInstance(organization_id=ctx.org_id, definition_id=d.id, definition_key=d.key, name=d.name,
                                 status="selected", hired_by_id=ctx.user.id)
            db.add(inst)
            db.flush()
            audit.record(db, "agents.hired", actor_id=ctx.user.id, org_id=ctx.org_id, target_type="agent_instance",
                         target_id=inst.id, data={"definition": d.key, "version": d.version, "source": source},
                         ip=ctx.meta.ip)
            created.append(inst)
        db.commit()
    except IntegrityError as exc:  # a concurrent hire of the same agent
        db.rollback()
        raise conflict("One of these agents was just hired by someone else") from exc
    return created


def list_instances(db: Session, ctx: OrgContext, include_retired: bool = False) -> list[s.InstanceListItem]:
    stmt = select(AgentInstance, AgentDefinition).join(AgentDefinition, AgentDefinition.id ==
                                                       AgentInstance.definition_id) \
        .where(AgentInstance.organization_id == ctx.org_id).order_by(AgentDefinition.letter)
    if not include_retired:
        stmt = stmt.where(AgentInstance.status != "retired")
    rows = db.execute(stmt).all()
    configs = {c.id: c for c in db.scalars(select(AgentConfiguration).where(
        AgentConfiguration.id.in_([i.current_config_id for i, _ in rows if i.current_config_id])))}
    counts = dict(db.execute(select(TaskDefinition.configuration_id, func.count())
                             .where(TaskDefinition.configuration_id.in_(list(configs)))
                             .group_by(TaskDefinition.configuration_id)).all())
    out = []
    for inst, d in rows:
        c = configs.get(inst.current_config_id)
        out.append(s.InstanceListItem(
            **s.InstanceOut.model_validate(inst).model_dump(), letter=d.letter, department=d.department,
            current_version=c.version if c else None, current_config_status=c.status if c else None,
            task_count=counts.get(c.id, 0) if c else 0,
            monthly_budget_usd=Decimal(str(c.config["limits"]["monthly_budget_usd"])) if c else None))
    return out


def retire(db: Session, ctx: OrgContext, inst: AgentInstance, reason: str | None) -> AgentInstance:
    previous = lifecycle.transition(inst, "retired", reason)
    audit.record(db, "agents.retired", actor_id=ctx.user.id, org_id=ctx.org_id, target_type="agent_instance",
                 target_id=inst.id, data={"from": previous}, ip=ctx.meta.ip)
    db.commit()
    db.refresh(inst)
    return inst


# ---- configurations ----------------------------------------------------------------------------------------------

def _canonical_tasks(tasks: list[s.TaskIn]) -> list[dict]:
    out = []
    for t in sorted(tasks, key=lambda t: t.key):
        d = t.model_dump(mode="json")
        d["depends_on"] = sorted(d["depends_on"])
        d["policy_refs"] = sorted(d["policy_refs"])
        d["required_permissions"] = sorted(d["required_permissions"])
        out.append(d)
    return out


def config_hash(config: s.AgentConfig, tasks: list[s.TaskIn]) -> str:
    material = {"config": config.model_dump(mode="json"), "tasks": _canonical_tasks(tasks)}
    return hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def task_rows(db: Session, cfg: AgentConfiguration) -> list[TaskDefinition]:
    return list(db.scalars(select(TaskDefinition).where(TaskDefinition.configuration_id == cfg.id)
                           .order_by(TaskDefinition.position)))


def _deps(db: Session, rows: list[TaskDefinition]) -> dict[uuid.UUID, list[str]]:
    key_of = {r.id: r.key for r in rows}
    out: dict[uuid.UUID, list[str]] = {r.id: [] for r in rows}
    if rows:
        for dep in db.scalars(select(TaskDependency).where(TaskDependency.task_id.in_(list(key_of)))):
            out[dep.task_id].append(key_of.get(dep.depends_on_id, "?"))
    return {k: sorted(v) for k, v in out.items()}


def _row_to_task(row: TaskDefinition, depends_on: list[str]) -> s.TaskIn:
    return s.TaskIn.model_validate({
        "key": row.key, "title": row.title, "description": row.description,
        "trigger": {"type": row.trigger_type, "schedule": row.schedule, "event": row.event},
        "inputs": row.inputs, "actions": row.actions, "expected_output": row.expected_output,
        "completion_criteria": row.completion_criteria, "depends_on": depends_on, "priority": row.priority,
        "sla_minutes": row.sla_minutes, "policy_refs": row.policy_refs,
        "required_permissions": row.required_permissions, "approval_required": row.approval_required,
        "approval_reason": row.approval_reason, "failure": row.failure})


def stored_document(db: Session, cfg: AgentConfiguration) -> tuple[s.AgentConfig, list[s.TaskIn]]:
    rows = task_rows(db, cfg)
    deps = _deps(db, rows)
    return s.AgentConfig.model_validate(cfg.config), [_row_to_task(r, deps[r.id]) for r in rows]


def recompute_hash(db: Session, cfg: AgentConfiguration) -> str | None:
    """Hash of what is in the database now. Differs from `config_hash` if anything changed behind the API."""
    try:
        config, tasks = stored_document(db, cfg)
    except ValidationError:
        return None
    return config_hash(config, tasks)


def _write_tasks(db: Session, inst: AgentInstance, cfg: AgentConfiguration, tasks: list[s.TaskIn]) -> None:
    for old in task_rows(db, cfg):
        db.delete(old)
    db.flush()
    rows: dict[str, TaskDefinition] = {}
    for i, t in enumerate(tasks):
        row = TaskDefinition(
            organization_id=inst.organization_id, configuration_id=cfg.id, instance_id=inst.id, key=t.key,
            position=i, title=t.title, description=t.description, trigger_type=t.trigger.type,
            schedule=t.trigger.schedule.model_dump() if t.trigger.schedule else None, event=t.trigger.event,
            inputs=t.inputs, actions=t.actions, expected_output=t.expected_output,
            completion_criteria=t.completion_criteria, priority=t.priority, sla_minutes=t.sla_minutes,
            policy_refs=[str(r) for r in t.policy_refs], required_permissions=list(t.required_permissions),
            approval_required=t.approval_required, approval_reason=t.approval_reason,
            failure=t.failure.model_dump())
        db.add(row)
        rows[t.key] = row
    db.flush()
    for t in tasks:
        for d in t.depends_on:
            if d in rows and d != t.key:  # unknown/self references are reported as issues, not stored
                db.add(TaskDependency(organization_id=inst.organization_id, task_id=rows[t.key].id,
                                      depends_on_id=rows[d].id))


def validation_context(db: Session, inst: AgentInstance) -> validation.Context:
    d = db.get(AgentDefinition, inst.definition_id)
    p = company.get_profile(db, inst.organization_id)
    others = Decimal(0)
    for other in db.scalars(select(AgentInstance).where(AgentInstance.organization_id == inst.organization_id,
                                                        AgentInstance.status != "retired",
                                                        AgentInstance.id != inst.id)):
        if other.current_config_id and (c := db.get(AgentConfiguration, other.current_config_id)):
            others += Decimal(str(c.config["limits"]["monthly_budget_usd"]))
    confirmed = {str(r.id) for r in rules_service.confirmed_for(db, inst.organization_id)}
    return validation.Context(spec=d.spec, timezone=p.timezone, operating_schedule=p.operating_schedule,
                              company_budget=p.monthly_ai_budget, company_currency=p.budget_currency,
                              other_agents_budget=others, confirmed_rule_ids=confirmed)


def issues_for(db: Session, inst: AgentInstance, config: s.AgentConfig, tasks: list[s.TaskIn]) -> list[s.Issue]:
    return validation.check(config, tasks, validation_context(db, inst))


def current_config(db: Session, inst: AgentInstance) -> AgentConfiguration | None:
    return db.get(AgentConfiguration, inst.current_config_id) if inst.current_config_id else None


def _store(db: Session, ctx: OrgContext, inst: AgentInstance, config: s.AgentConfig, tasks: list[s.TaskIn], *,
           source: str, generation: dict) -> AgentConfiguration:
    """Overwrite the current draft, or start the next version if the current one is frozen."""
    if inst.status not in LIVE_EDIT_STATES:
        raise AppError(409, "invalid_transition", "A retired agent can't be reconfigured")
    cfg = current_config(db, inst)
    digest = config_hash(config, tasks)
    if cfg is not None and cfg.status == "draft":
        cfg.config, cfg.config_hash, cfg.source = config.model_dump(mode="json"), digest, source
        if generation:
            cfg.generation = generation
    else:
        if cfg is not None and cfg.status == "submitted":
            cfg.status = "withdrawn"  # superseded before a decision; the inbox no longer shows it
        version = (db.scalar(select(func.max(AgentConfiguration.version))
                             .where(AgentConfiguration.instance_id == inst.id)) or 0) + 1
        cfg = AgentConfiguration(organization_id=inst.organization_id, instance_id=inst.id, version=version,
                                 status="draft", config=config.model_dump(mode="json"), config_hash=digest,
                                 source=source, generation=generation or (cfg.generation if cfg else {}),
                                 created_by_id=ctx.user.id)
        db.add(cfg)
        db.flush()
        inst.current_config_id = cfg.id
    _write_tasks(db, inst, cfg, tasks)
    lifecycle.transition(inst, "configuring", "Configuration is being edited")
    return cfg


def generate(db: Session, ctx: OrgContext, inst: AgentInstance) -> AgentConfiguration:
    d = db.get(AgentDefinition, inst.definition_id)
    profile = company.get_profile(db, ctx.org_id)
    spec = {**d.spec, "_version": d.version}
    confirmed = rules_service.confirmed_for(db, ctx.org_id, d.key)
    open_rules = [r for r in db.scalars(select(BusinessRule).where(
        BusinessRule.organization_id == ctx.org_id,
        BusinessRule.status.in_(("fact", "proposed", "unresolved", "conflicting"))))
        if not r.applies_to or d.key in r.applies_to]
    answers = [(q.question, q.answer or "") for q in db.scalars(select(InterviewQuestion).where(
        InterviewQuestion.organization_id == ctx.org_id, InterviewQuestion.status == "answered"))]
    caller = gateway.Caller(ctx.org_id, ctx.user.id, inst.id)
    config, tasks, meta = design.generate(db, caller, spec, profile, confirmed, open_rules, answers)
    cfg = _store(db, ctx, inst, config, tasks, source="generated", generation=meta)
    audit.record(db, "agents.config_generated", actor_id=ctx.user.id, org_id=ctx.org_id,
                 target_type="agent_configuration", target_id=cfg.id,
                 data={"version": cfg.version, "provider": meta["provider"], "rules_used": len(meta["rules_used"])},
                 ip=ctx.meta.ip)
    db.commit()
    return cfg


def save_draft(db: Session, ctx: OrgContext, inst: AgentInstance, draft: s.DraftIn) -> AgentConfiguration:
    cfg = _store(db, ctx, inst, draft.config, draft.tasks, source="edited", generation={})
    audit.record(db, "agents.config_edited", actor_id=ctx.user.id, org_id=ctx.org_id,
                 target_type="agent_configuration", target_id=cfg.id,
                 data={"version": cfg.version, "hash": cfg.config_hash}, ip=ctx.meta.ip)
    db.commit()
    return cfg


def submit(db: Session, ctx: OrgContext, inst: AgentInstance) -> AgentConfiguration:
    cfg = current_config(db, inst)
    if cfg is None or cfg.status != "draft":
        raise AppError(409, "nothing_to_submit", "There is no draft configuration to submit")
    config, tasks = stored_document(db, cfg)
    issues = issues_for(db, inst, config, tasks)
    if validation.has_errors(issues):
        raise AppError(409, "config_invalid", "Fix the configuration errors before submitting",
                       [i.model_dump() for i in issues if i.severity == "error"])
    lifecycle.transition(inst, "awaiting_approval", "Submitted for the CEO's approval")
    cfg.status, cfg.submitted_by_id, cfg.submitted_at = "submitted", ctx.user.id, datetime.now(UTC)
    audit.record(db, "agents.config_submitted", actor_id=ctx.user.id, org_id=ctx.org_id,
                 target_type="agent_configuration", target_id=cfg.id,
                 data={"version": cfg.version, "hash": cfg.config_hash}, ip=ctx.meta.ip)
    db.commit()
    return cfg


def config_out(db: Session, inst: AgentInstance, cfg: AgentConfiguration) -> s.ConfigOut:
    rows = task_rows(db, cfg)
    deps = _deps(db, rows)
    try:
        config, tasks = s.AgentConfig.model_validate(cfg.config), [_row_to_task(r, deps[r.id]) for r in rows]
        issues = issues_for(db, inst, config, tasks) if cfg.status in ("draft", "submitted") else []
    except ValidationError:
        issues = [s.Issue(severity="error", field="config", message="The stored configuration is not valid")]
    return s.ConfigOut(**s.ConfigSummaryOut.model_validate(cfg).model_dump(), config=cfg.config,
                       generation=cfg.generation,
                       tasks=[s.TaskOut.model_validate(r).model_copy(update={"depends_on": deps[r.id]}) for r in rows],
                       issues=issues)


def get_version(db: Session, inst: AgentInstance, version: int) -> AgentConfiguration:
    cfg = db.scalar(select(AgentConfiguration).where(AgentConfiguration.instance_id == inst.id,
                                                     AgentConfiguration.version == version))
    if cfg is None:
        raise not_found("Configuration version")
    return cfg


def versions(db: Session, inst: AgentInstance) -> list[AgentConfiguration]:
    return list(db.scalars(select(AgentConfiguration).where(AgentConfiguration.instance_id == inst.id)
                           .order_by(AgentConfiguration.version.desc())))


# ---- execution guard ---------------------------------------------------------------------------------------------

OBSERVATION_SCOPES = ("data.read", "records.draft")


def execution_allowed(db: Session, inst: AgentInstance, scope: str | None = None, *,
                      approved_action: bool = False) -> tuple[bool, str]:
    """The single check every real tool call passes before any execution (orchestration calls it before the
    dispatcher and again right before the tool runs). True only for an active agent whose current configuration is
    the approved one, unchanged since the recorded approval (hash re-computed from the DB). With a scope, also checks
    the deployment stage: in observation only reading and drafting run — unless a person approved this exact action
    (`approved_action`, an approved action request bound to its parameters). The scope's own mode in the
    configuration — denied / approval required — is the dispatcher's check."""
    if inst.status != "active":
        return False, f"Agent is {lifecycle.LABELS.get(inst.status, inst.status).lower()}, not active"
    if inst.approved_config_id is None or inst.approved_config_id != inst.current_config_id:
        return False, "The current configuration has not been approved"
    cfg = db.get(AgentConfiguration, inst.approved_config_id)
    if cfg is None or cfg.status != "approved":
        return False, "The approved configuration is missing"
    if recompute_hash(db, cfg) != cfg.config_hash:
        return False, "The configuration changed after it was approved"
    approval = db.scalar(select(Approval).where(Approval.subject_type == "agent_configuration",
                                                Approval.subject_id == cfg.id)
                         .order_by(Approval.created_at.desc()))
    if approval is None or approval.decision != "approved" or approval.subject_hash != cfg.config_hash:
        return False, "No approval is recorded for this exact configuration"
    if inst.deployment_stage not in ("observation", "full"):
        return False, "The agent has not been activated"
    if scope is not None and inst.deployment_stage == "observation" and scope not in OBSERVATION_SCOPES \
            and not approved_action:
        return False, "Observation stage: only reading and drafting are allowed"
    stage = "observation stage" if inst.deployment_stage == "observation" else "full permissions"
    return True, f"Approved configuration v{cfg.version}, {stage}"


# ---- views -------------------------------------------------------------------------------------------------------

def approvals_for(db: Session, inst: AgentInstance) -> list[Approval]:
    return list(db.scalars(select(Approval).where(Approval.instance_id == inst.id)
                           .order_by(Approval.created_at.desc()).limit(50)))


def detail(db: Session, ctx: OrgContext, inst: AgentInstance) -> s.InstanceDetailOut:
    from abos.governance.approvals import approval_out  # noqa: PLC0415 — governance imports this module

    d = db.get(AgentDefinition, inst.definition_id)
    cfg = current_config(db, inst)
    allowed, reason = execution_allowed(db, inst)
    return s.InstanceDetailOut(
        **s.InstanceOut.model_validate(inst).model_dump(), definition=definition_out(d, inst.status, inst.id),
        current_config=config_out(db, inst, cfg) if cfg else None,
        approvals=[approval_out(db, a) for a in approvals_for(db, inst)],
        execution={"allowed": allowed, "reason": reason})


def schedule_preview(db: Session, inst: AgentInstance, cfg: AgentConfiguration, n: int = 5) -> s.SchedulePreviewOut:
    p = company.get_profile(db, inst.organization_id)
    config = cfg.config
    window = config["operating"]["execution_window"]
    holidays = schedule.holiday_dates(p.holidays)
    now = datetime.now(UTC)
    tasks, notes = [], []
    for row in task_rows(db, cfg):
        item = {"key": row.key, "title": row.title, "trigger_type": row.trigger_type, "event": row.event,
                "schedule": row.schedule, "next_runs": []}
        if row.trigger_type == "schedule" and p.timezone and row.schedule:
            item["next_runs"] = [t.isoformat() for t in schedule.next_runs(
                row.schedule, tz=p.timezone, after=now, n=n, window=window,
                operating_schedule=p.operating_schedule, holidays=holidays)]
        tasks.append(item)
    if not p.timezone:
        notes.append("Set the company time zone to calculate run times.")
    if window == "business_hours":
        notes.append("Routine work runs only in business hours: weekly runs on closed days or holidays are skipped, "
                     "monthly runs move to the next opening, and events noticed after hours wait for the next opening.")
    if config["operating"]["critical_alerts"] == "immediate":
        notes.append("Critical alerts are delivered immediately, at any hour.")
    if config["operating"]["monitoring"] == "continuous":
        notes.append("Monitoring runs continuously, separately from the execution window.")
    return s.SchedulePreviewOut(timezone=p.timezone, execution_window=window, tasks=tasks, notes=notes)
