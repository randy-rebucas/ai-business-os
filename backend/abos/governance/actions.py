"""Approval of held tool actions (SPEC §6 'Human approval', ADR-026).

When the dispatcher holds a call, the orchestrator raises an `ActionRequest` with the exact parameters the action
would use (e.g. recipient, subject and full text of a reminder) and a hash binding them to the agent's configuration
hash and the policy version. The approver decides on what they saw: the decision must carry that hash. When the run
resumes, the parameters are resolved again; only an approved request with an identical hash lets the action run, and
it is used once. Anything different — an edited draft, a new confirmed rule, a new configuration — supersedes the
approval and raises a new request.
"""

import hashlib
import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from abos.audit import service as audit
from abos.core.errors import AppError, not_found
from abos.governance.models import ActionRequest, Approval
from abos.identity.deps import OrgContext
from abos.identity.models import User


def params_hash(*, tool: str, parameters: dict, instance_id: uuid.UUID, config_hash: str, policy_version: str) -> str:
    material = {"tool": tool, "parameters": parameters, "instance": str(instance_id), "config": config_hash,
                "policy": policy_version}
    return hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":"), default=str)
                          .encode()).hexdigest()


def for_step(db: Session, run_id: uuid.UUID, step_no: int) -> list[ActionRequest]:
    return list(db.scalars(select(ActionRequest).where(ActionRequest.run_id == run_id,
                                                       ActionRequest.step_no == step_no)
                           .order_by(ActionRequest.created_at)))


def raise_request(db: Session, run, *, step_no: int, tool, data: dict, parameters: dict, digest: str,
                  policy_version: str, reason: str) -> ActionRequest:
    """The pending request for this exact action, creating it (and superseding stale ones) if needed."""
    for old in for_step(db, run.id, step_no):
        if old.params_hash == digest and old.status == "pending":
            return old
        if old.status in ("pending", "approved"):
            old.status = "superseded"
    req = ActionRequest(organization_id=run.organization_id, run_id=run.id, instance_id=run.instance_id,
                        step_no=step_no, tool=tool.key, tool_label=tool.label, scope=tool.scope, risk=tool.risk,
                        input=data, parameters=parameters, params_hash=digest, config_hash=run.config_hash,
                        policy_version=policy_version, reason=reason[:500])
    db.add(req)
    db.flush()
    audit.record(db, "approvals.action_requested", actor_type="agent", org_id=run.organization_id,
                 target_type="action_request", target_id=req.id,
                 data={"tool": tool.key, "run_id": str(run.id), "hash": digest, "reason": reason[:200]})
    from abos.notifications import service as notifications  # noqa: PLC0415

    notifications.notify(db, run.organization_id, kind="action_required", severity="warning",
                         title=f"Approval needed: {tool.label}", body=f"{run.task_title} — {reason[:300]}",
                         link="/app/approvals", subject_type="action_request", subject_id=req.id,
                         dedupe=f"action:{req.id}")
    return req


def approved_for(db: Session, run_id: uuid.UUID, step_no: int, digest: str) -> ActionRequest | None:
    return next((r for r in for_step(db, run_id, step_no) if r.status == "approved" and r.params_hash == digest),
                None)


def rejected_for(db: Session, run_id: uuid.UUID, step_no: int, digest: str) -> ActionRequest | None:
    return next((r for r in for_step(db, run_id, step_no) if r.status == "rejected" and r.params_hash == digest),
                None)


# ---- people ------------------------------------------------------------------------------------------------------

def get(db: Session, ctx: OrgContext, request_id: uuid.UUID) -> ActionRequest:
    req = db.get(ActionRequest, request_id)
    if req is None or req.organization_id != ctx.org_id:
        raise not_found("Action request")
    return req


def listing(db: Session, ctx: OrgContext, status: str | None = None, limit: int = 100) -> list[ActionRequest]:
    stmt = select(ActionRequest).where(ActionRequest.organization_id == ctx.org_id)
    if status:
        stmt = stmt.where(ActionRequest.status == status)
    return list(db.scalars(stmt.order_by(ActionRequest.created_at.desc()).limit(limit)))


def decide(db: Session, ctx: OrgContext, request_id: uuid.UUID, decision: str, note: str | None,
           reviewed_hash: str) -> ActionRequest:
    from abos.orchestration import service as orchestration  # noqa: PLC0415 — orchestration imports this module

    req = get(db, ctx, request_id)
    if req.status != "pending":
        raise AppError(409, "not_pending", f"This action is {req.status}, not waiting for a decision")
    if reviewed_hash != req.params_hash:
        raise AppError(409, "action_changed", "The action changed since you reviewed it; review it again")
    if decision == "rejected" and not (note or "").strip():
        raise AppError(422, "note_required", "Say why the action is rejected")
    approval = Approval(organization_id=ctx.org_id, subject_type="tool_action", subject_id=req.id,
                        instance_id=req.instance_id, subject_version=None, subject_hash=req.params_hash,
                        policy_version=req.policy_version, decision=decision, note=note or None,
                        scope={"tool": req.tool, "scope": req.scope, "parameters": req.parameters,
                               "run_id": str(req.run_id), "step_no": req.step_no, "config_hash": req.config_hash},
                        decided_by_id=ctx.user.id, decided_by_role=ctx.role)
    db.add(approval)
    db.flush()
    req.status, req.note, req.decided_by_id, req.decided_by_role = decision, note or None, ctx.user.id, ctx.role
    req.decided_at, req.approval_id = datetime.now(UTC), approval.id
    audit.record(db, f"approvals.action_{decision}", actor_id=ctx.user.id, org_id=ctx.org_id,
                 target_type="action_request", target_id=req.id,
                 data={"tool": req.tool, "hash": req.params_hash, "run_id": str(req.run_id),
                       "approval_id": str(approval.id)}, ip=ctx.meta.ip)
    orchestration.resume_after_decision(db, req)
    db.commit()
    db.refresh(req)
    return req


def out(db: Session, req: ActionRequest) -> dict:
    from abos.agents.models import AgentInstance  # noqa: PLC0415
    from abos.orchestration.models import WorkflowRun  # noqa: PLC0415

    inst = db.get(AgentInstance, req.instance_id)
    run = db.get(WorkflowRun, req.run_id)
    user = db.get(User, req.decided_by_id) if req.decided_by_id else None
    return {"id": req.id, "run_id": req.run_id, "instance_id": req.instance_id,
            "agent_name": inst.name if inst else None, "task_title": run.task_title if run else None,
            "step_no": req.step_no, "tool": req.tool, "tool_label": req.tool_label, "scope": req.scope,
            "risk": req.risk, "parameters": req.parameters,
            "params_hash": req.params_hash, "config_hash": req.config_hash, "policy_version": req.policy_version,
            "reason": req.reason, "status": req.status, "note": req.note, "decided_by_name": user.full_name if user
            else None, "decided_by_role": req.decided_by_role, "decided_at": req.decided_at,
            "created_at": req.created_at}
