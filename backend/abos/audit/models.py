import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from abos.core.db import Base, IdMixin


class AuditEvent(IdMixin, Base):
    """Append-only. UPDATE/DELETE are rejected by a database trigger and not granted to the app role."""

    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_org_created", "organization_id", "created_at"),)
    # No INSERT ... RETURNING: Postgres checks RETURNING rows against the RLS read policy, and platform events
    # (organization_id NULL) are deliberately unreadable outside system scope.
    __mapper_args__ = {"eager_defaults": False}

    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    # Later phases: an agent can be the actor (actor_type="agent", actor_agent_id) — the user stays the authoriser.
    actor_type: Mapped[str] = mapped_column(String(20), default="user")  # user | agent | system
    action: Mapped[str] = mapped_column(String(80), index=True)
    target_type: Mapped[str | None] = mapped_column(String(60))
    target_id: Mapped[str | None] = mapped_column(String(64))
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    ip: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
