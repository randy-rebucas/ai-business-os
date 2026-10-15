import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from abos.audit.models import AuditEvent


def record(
    db: Session,
    action: str,
    *,
    actor_id: uuid.UUID | None = None,
    actor_type: str = "user",
    org_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: Any = None,
    data: dict[str, Any] | None = None,
    ip: str | None = None,
) -> AuditEvent:
    """Add an audit event to the caller's transaction. The caller commits, so the event exists iff the change does."""
    event = AuditEvent(
        action=action,
        actor_user_id=actor_id,
        actor_type=actor_type,
        organization_id=org_id,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        data=data or {},
        ip=ip,
    )
    db.add(event)
    return event


def search(db: Session, *, org_id: uuid.UUID, action: str | None = None, actor_id: uuid.UUID | None = None,
           target_type: str | None = None, limit: int = 50, before: datetime | None = None) -> list[AuditEvent]:
    stmt = (select(AuditEvent).where(AuditEvent.organization_id == org_id)
            .order_by(AuditEvent.created_at.desc()).limit(min(limit, 200)))
    if action:
        stmt = stmt.where(AuditEvent.action.startswith(action))
    if actor_id:
        stmt = stmt.where(AuditEvent.actor_user_id == actor_id)
    if target_type:
        stmt = stmt.where(AuditEvent.target_type == target_type)
    if before is not None:
        stmt = stmt.where(AuditEvent.created_at < before)
    return list(db.scalars(stmt))
