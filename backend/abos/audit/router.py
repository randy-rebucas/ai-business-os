import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from abos.audit import service
from abos.core.db import get_db
from abos.identity.deps import OrgContext, require_org_permission
from abos.identity.models import User

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    actor_user_id: uuid.UUID | None
    actor_type: str
    actor_name: str | None = None
    action: str
    target_type: str | None
    target_id: str | None
    data: dict[str, Any]
    created_at: datetime


@router.get("", response_model=list[AuditOut])
def org_audit(action: str | None = Query(None, max_length=80), actor_id: uuid.UUID | None = None,
              target_type: str | None = Query(None, max_length=60), before: datetime | None = None,
              limit: int = Query(50, ge=1, le=200),
              ctx: OrgContext = Depends(require_org_permission("audit.read")), db: Session = Depends(get_db)):
    events = service.search(db, org_id=ctx.org_id, action=action, actor_id=actor_id, target_type=target_type,
                            limit=limit, before=before)
    ids = {e.actor_user_id for e in events if e.actor_user_id}
    names = dict(db.execute(select(User.id, User.full_name).where(User.id.in_(ids))).all()) if ids else {}
    out = []
    for e in events:
        item = AuditOut.model_validate(e)
        item.actor_name = names.get(e.actor_user_id)
        out.append(item)
    return out
