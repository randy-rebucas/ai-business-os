import uuid
from typing import Any

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from abos.core.db import Base, IdMixin, TenantMixin, TimestampMixin


class WorkspaceBranding(IdMixin, TimestampMixin, TenantMixin, Base):
    """One row per workspace once anything is customised; absent = platform defaults + mood from the industry."""

    __tablename__ = "workspace_branding"
    __table_args__ = (UniqueConstraint("organization_id", name="uq_workspace_branding_org"),)

    logo_key: Mapped[str | None] = mapped_column(String(200))
    logo_width: Mapped[int | None] = mapped_column(Integer)
    logo_height: Mapped[int | None] = mapped_column(Integer)
    logo_palette: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)  # [{hex, share}]
    # Where the accent comes from: platform | logo | owner (picked by hand). owner_accent holds the picked colour.
    accent_source: Mapped[str] = mapped_column(String(10), default="platform")
    owner_accent: Mapped[str | None] = mapped_column(String(7))
    # Type mood: None = follow the industry; otherwise a key of branding.moods.MOODS chosen by an owner/admin.
    mood: Mapped[str | None] = mapped_column(String(20))
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
