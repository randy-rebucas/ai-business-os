"""CEO review & approval of agent configurations (SPEC §3 step 5, §6 'Human approval').

A decision is accepted only for the agent's current, submitted configuration, and only if the hash the approver
reviewed equals both the stored hash and a hash re-computed from the rows right now — so an edit made while the CEO
was reading (or a change behind the API) forces a fresh review. Errors are re-checked at decision time because rules
or company hours may have changed since submission. Each decision is an insert-only `approvals` row recording who,
when, the decision, the configuration version and hash, the policy version and the exact scope authorised.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from abos.agents import lifecycle
from abos.agents import service as agents
from abos.agents.models import AgentConfiguration, AgentInstance
from abos.agents.schemas import ApprovalOut
from abos.audit import service as audit
from abos.core.errors import AppError, not_found
from abos.governance import rules
from abos.governance.models import Approval
from abos.identity.deps import OrgContext
from abos.identity.models import User


def approval_out(db: Session, a: Approval) -> ApprovalOut:
    user = db.get(User, a.decided_by_id) if a.decided_by_id else None
    return ApprovalOut.model_validate(a).model_copy(update={"decided_by_name": user.full_name if user else None})


def scope_of(config: dict, tasks: list) -> dict:
    """What an approval authorises, in the approver's terms."""
    return {
        "automation_level": config["automation_level"],
        "operating": config["operating"],
        "permissions": {k: v for k, v in config["permissions"].items() if v != "denied"},
        "knowledge": config["knowledge"],
        "monthly_budget_usd": str(config["limits"]["monthly_budget_usd"]),
        "max_runs_per_day": config["limits"]["max_runs_per_day"],
        "tools": config["job"]["authorized_tools"],
        "tasks": [{"key": t.key, "title": t.title, "trigger": t.trigger.model_dump(mode="json"),
                   "required_permissions": list(t.required_permissions), "approval_required": t.approval_required}
                  for t in tasks],
    }


def pending(db: Session, ctx: OrgContext) -> list[dict]:
    rows = db.execute(select(AgentConfiguration, AgentInstance)
                      .join(AgentInstance, AgentInstance.current_config_id == AgentConfiguration.id)
                      .where(AgentConfiguration.organization_id == ctx.org_id,
                             AgentConfiguration.status == "submitted")
                      .order_by(AgentConfiguration.submitted_at)).all()
    out = []
    for cfg, inst in rows:
        submitter = db.get(User, cfg.submitted_by_id) if cfg.submitted_by_id else None
        out.append({"config_id": cfg.id, "instance_id": inst.id, "agent_name": inst.name,
                    "definition_key": inst.definition_key, "version": cfg.version, "config_hash": cfg.config_hash,
                    "submitted_at": cfg.submitted_at, "submitted_by": submitter.full_name if submitter else None,
                    "task_count": len(agents.task_rows(db, cfg))})
    return out


def history(db: Session, ctx: OrgContext, limit: int = 100) -> list[ApprovalOut]:
    rows = db.scalars(select(Approval).where(Approval.organization_id == ctx.org_id)
                      .order_by(Approval.created_at.desc()).limit(limit))
    return [approval_out(db, a) for a in rows]


def get_config(db: Session, ctx: OrgContext, config_id: uuid.UUID) -> tuple[AgentConfiguration, AgentInstance]:
    cfg = db.get(AgentConfiguration, config_id)
    if cfg is None or cfg.organization_id != ctx.org_id:
        raise not_found("Configuration")
    return cfg, db.get(AgentInstance, cfg.instance_id)


def decide(db: Session, ctx: OrgContext, config_id: uuid.UUID, decision: str, note: str | None,
           reviewed_hash: str) -> Approval:
    cfg, inst = get_config(db, ctx, config_id)
    if cfg.status != "submitted" or inst.current_config_id != cfg.id:
        raise AppError(409, "not_pending", "This configuration is not waiting for a decision")
    actual = agents.recompute_hash(db, cfg)
    if reviewed_hash != cfg.config_hash or actual != cfg.config_hash:
        raise AppError(409, "config_changed", "The configuration changed since you reviewed it; review it again")
    config, tasks = agents.stored_document(db, cfg)
    if decision == "approved":
        errors = [i for i in agents.issues_for(db, inst, config, tasks) if i.severity == "error"]
        if errors:
            raise AppError(409, "config_invalid", "The configuration no longer passes validation",
                           [i.model_dump() for i in errors])
    if decision == "rejected" and not (note or "").strip():
        raise AppError(422, "note_required", "Say what should change so the configuration can be revised")
    approval = Approval(organization_id=ctx.org_id, subject_type="agent_configuration", subject_id=cfg.id,
                        instance_id=inst.id, subject_version=cfg.version, subject_hash=cfg.config_hash,
                        policy_version=rules.policy_version(db, ctx.org_id), decision=decision, note=note or None,
                        scope=scope_of(cfg.config, tasks), decided_by_id=ctx.user.id, decided_by_role=ctx.role)
    db.add(approval)
    cfg.decided_at = datetime.now(UTC)
    if decision == "approved":
        cfg.status = "approved"
        inst.approved_config_id = cfg.id
        # Phase 4 runs readiness simulations while the agent is in `testing`.
        lifecycle.transition(inst, "testing", f"Configuration v{cfg.version} approved")
    else:
        cfg.status = "rejected"
        lifecycle.transition(inst, "configuring", f"Changes requested: {note}")
    db.flush()
    audit.record(db, f"approvals.{decision}", actor_id=ctx.user.id, org_id=ctx.org_id,
                 target_type="agent_configuration", target_id=cfg.id,
                 data={"approval_id": str(approval.id), "version": cfg.version, "hash": cfg.config_hash,
                       "policy_version": approval.policy_version, "agent": inst.definition_key}, ip=ctx.meta.ip)
    db.commit()
    db.refresh(approval)
    return approval
