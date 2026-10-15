import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

from abos.simulation.models import CATEGORIES

Category = Literal["normal", "missing_information", "conflicting_policies", "outdated_documents",
                   "unauthorized_request", "insufficient_permissions", "failed_integration", "transient_error",
                   "duplicate_execution", "financial_discrepancy", "escalation", "malicious_document", "cross_tenant",
                   "approval_required"]
assert set(Category.__args__) == set(CATEGORIES)  # noqa: S101
Text = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
Short = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ScenarioOut(ORM):
    id: uuid.UUID
    agent_key: str
    key: str
    version: int
    category: str
    title: str
    description: str
    input: dict[str, Any]
    fixtures: dict[str, Any]
    scripted_plan: list[dict[str, Any]]
    assertions: list[dict[str, Any]]
    expected_outcome: str
    required: bool
    is_active: bool
    source: str


class ScenarioIn(BaseModel):
    """A custom scenario described by expectations; the platform turns them into deterministic assertions."""

    agent_key: Literal["executive", "sales", "finance", "marketing", "operations", "procurement", "hr", "support"]
    category: Category = "normal"
    title: Short
    description: Text | None = None
    request: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=2000)]
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=1000)] | None = None
    expected_answer_contains: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None = None
    answer_must_not_contain: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None = None
    must_escalate: bool = False
    forbidden_tool: Annotated[str, StringConstraints(max_length=60)] | None = None
    required: bool = True


class RunOut(ORM):
    id: uuid.UUID
    instance_id: uuid.UUID
    configuration_id: uuid.UUID
    config_version: int
    config_hash: str
    policy_version: str
    status: str
    passed: bool | None
    planner: dict[str, Any]
    suite: list[dict[str, Any]]
    scores: dict[str, Any]
    thresholds: dict[str, Any]
    summary: dict[str, Any]
    error: str | None
    created_at: datetime
    finished_at: datetime | None
    agent_name: str | None = None


class ResultOut(ORM):
    id: uuid.UUID
    scenario_id: uuid.UUID | None
    scenario_key: str
    scenario_version: int
    category: str
    title: str
    passed: bool
    mandatory_failed: bool
    outcome: str
    trace: list[dict[str, Any]]
    output: dict[str, Any]
    assertions: list[dict[str, Any]]
    analysis: dict[str, Any]


class RunDetailOut(RunOut):
    results: list[ResultOut]
    progress: list[dict[str, Any]] = []


class ReviewedIn(BaseModel):
    config_hash: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)] | None = None


class PauseIn(BaseModel):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] | None = None


class RollbackIn(BaseModel):
    version: int
