import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

AgentKey = Literal["executive", "sales", "finance", "marketing", "operations", "procurement", "hr", "support"]
Kind = Literal["policy", "workflow", "responsibility", "approval", "threshold", "customer_service", "operating_hours",
               "escalation", "reporting", "objective", "recurring", "dependency"]
Statement = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=2000)]


class RuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    status: str
    title: str
    statement: str
    source_type: str
    citations: list[dict[str, Any]]
    source_ref: str | None
    access_level: str
    applies_to: list[str]
    threshold_amount: Decimal | None
    threshold_currency: str | None
    conflicts_with: list[str]
    resolution: str | None
    provider: str
    label: str | None
    reviewed_at: datetime | None
    created_at: datetime
    stale: str | None = None  # computed: the cited document is no longer indexed


class ExtractOut(BaseModel):
    created: int
    existing: int
    conflicts: int
    dropped: list[dict[str, Any]]
    provider: str
    label: str | None
    sources_considered: int


class RuleReviewIn(BaseModel):
    decision: Literal["confirm", "reject"]
    resolution: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] | None = None
    statement: Statement | None = None
    applies_to: Annotated[list[AgentKey], Field(max_length=8)] | None = None


class RuleCreateIn(BaseModel):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=300)]
    statement: Statement
    kind: Kind = "policy"
    applies_to: Annotated[list[AgentKey], Field(max_length=8)] = []


class DecideIn(BaseModel):
    decision: Literal["approved", "rejected"]
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] | None = None
    config_hash: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class PendingOut(BaseModel):
    config_id: uuid.UUID
    instance_id: uuid.UUID
    agent_name: str
    definition_key: str
    version: int
    config_hash: str
    submitted_at: datetime | None
    submitted_by: str | None
    task_count: int
