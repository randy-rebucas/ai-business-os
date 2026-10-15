import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RetentionIn(BaseModel):
    """Bounds keep history useful for audits and budgets: nothing below 30 days, nothing above 10 years."""

    model_config = ConfigDict(extra="forbid")

    notifications_days: int = Field(ge=30, le=3650)
    ask_history_days: int = Field(ge=30, le=3650)
    reports_days: int | None = Field(default=None, ge=90, le=3650)  # None = keep daily reports


class RetentionOut(RetentionIn):
    kept: list[str]  # what is never purged while the workspace exists, and why — shown in settings


class DeletionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirm_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1, max_length=200)


class DeletionOut(BaseModel):
    scheduled_for: datetime | None
    requested_by_id: uuid.UUID | None
    grace_hours: int


class ExportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    size_bytes: int | None
    manifest: dict[str, Any]
    error: str | None
    created_at: datetime
    expires_at: datetime | None
