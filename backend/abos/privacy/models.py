import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from abos.core.db import Base, IdMixin, TenantMixin, TimestampMixin


class OrgExport(IdMixin, TimestampMixin, TenantMixin, Base):
    """A downloadable archive of one workspace's data (JSON per table + original documents), built by a job."""

    __tablename__ = "org_exports"

    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued | building | ready | failed | expired
    storage_key: Mapped[str | None] = mapped_column(String(200))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)  # table → row count, files, format
    error: Mapped[str | None] = mapped_column(String(300))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OrganizationDeletion(IdMixin, Base):
    """Platform record that a workspace was deleted: no tenant data, only what proves the deletion happened.
    Not a tenant table — it outlives the organization it describes."""

    __tablename__ = "organization_deletions"

    deleted_organization_id: Mapped[uuid.UUID] = mapped_column(index=True)  # no FK: the organization is gone
    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    rows_deleted: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)  # table → rows removed
    files_deleted: Mapped[int] = mapped_column(default=0)
    files_failed: Mapped[int] = mapped_column(default=0)
