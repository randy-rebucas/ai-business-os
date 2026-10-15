"""Agent configuration document (validated before storage, ADR-018) and API shapes.

Structural rules live here (types, lengths, enums, trigger shape). Rules that need context — the definition's
permission ceilings, the company's hours, confirmed business rules, budgets — live in `validation.py` and come back
as issues, so a draft can be saved while it still has problems but can't be submitted with errors.
"""

import re
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from abos.agents import policy

Line = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
Lines = Annotated[list[Line], Field(max_length=25)]
Para = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
Short = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]

Day = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
Scope = Literal["data.read", "records.draft", "records.modify", "comms.external", "transactions.create",
                "transactions.approve", "finance.execute", "documents.sensitive"]
DocType = Literal["policy", "sop", "handbook", "catalog", "pricing", "contract", "financial", "org_chart",
                  "job_description", "workflow", "script", "other"]
_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
TASK_KEY = re.compile(r"^[a-z0-9][a-z0-9-]{1,59}$")

assert set(Scope.__args__) == set(policy.SCOPES)  # noqa: S101 — keep the Literal and the scope map in sync


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def _hhmm(v: str) -> str:
    if not _HHMM.match(v):
        raise ValueError("Times must be HH:MM (24-hour)")
    return v


# ---- tasks -------------------------------------------------------------------------------------------------------

class WeeklySchedule(BaseModel):
    kind: Literal["weekly"]
    days: Annotated[list[Day], Field(min_length=1, max_length=7)]
    time: str

    _t = field_validator("time")(_hhmm)

    @field_validator("days")
    @classmethod
    def _unique(cls, v: list[str]) -> list[str]:
        order = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
        return sorted(set(v), key=order.index)


class MonthlySchedule(BaseModel):
    kind: Literal["monthly"]
    day: Annotated[int, Field(ge=1, le=28)]  # ≤ 28 so every month has the day
    time: str

    _t = field_validator("time")(_hhmm)


Schedule = Annotated[WeeklySchedule | MonthlySchedule, Field(discriminator="kind")]


class Trigger(BaseModel):
    type: Literal["schedule", "event", "on_demand"]
    schedule: Schedule | None = None
    event: str | None = None

    @model_validator(mode="after")
    def _shape(self) -> "Trigger":
        if self.type == "schedule" and self.schedule is None:
            raise ValueError("A scheduled task needs a schedule")
        if self.type == "event":
            if self.event not in policy.EVENTS:
                raise ValueError(f"Unknown event; use one of: {', '.join(policy.EVENTS)}")
        if self.type != "schedule":
            self.schedule = None
        if self.type != "event":
            self.event = None
        return self


class FailurePolicy(BaseModel):
    max_retries: Annotated[int, Field(ge=0, le=5)] = 2
    retry_backoff_minutes: Annotated[int, Field(ge=1, le=1440)] = 15
    on_failure: Literal["escalate", "notify", "skip"] = "escalate"


class TaskIn(BaseModel):
    key: str
    title: Short
    description: Para = ""
    trigger: Trigger
    inputs: Lines = []
    actions: Lines = []
    expected_output: Para = ""
    completion_criteria: Lines = []
    depends_on: Annotated[list[str], Field(max_length=20)] = []
    priority: Literal["low", "normal", "high", "critical"] = "normal"
    sla_minutes: Annotated[int, Field(ge=1, le=10080)] | None = None
    policy_refs: Annotated[list[uuid.UUID], Field(max_length=20)] = []
    required_permissions: Annotated[list[Scope], Field(max_length=8)] = []
    approval_required: bool = False
    approval_reason: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)] | None = None
    failure: FailurePolicy = FailurePolicy()

    @field_validator("key")
    @classmethod
    def _key(cls, v: str) -> str:
        if not TASK_KEY.match(v):
            raise ValueError("Task keys use lowercase letters, digits and hyphens (2–60 characters)")
        return v

    @field_validator("required_permissions", "depends_on")
    @classmethod
    def _dedupe(cls, v: list) -> list:
        return list(dict.fromkeys(v))


# ---- configuration -----------------------------------------------------------------------------------------------

class JobDescription(BaseModel):
    title: Short
    department: Short
    mission: Para
    scope: Para = ""
    included_tasks: Lines = []
    excluded_tasks: Lines = []
    required_knowledge: Lines = []
    data_sources: Lines = []
    authorized_tools: Annotated[list[str], Field(max_length=25)] = []  # tool keys from the catalog definition
    priority_rules: Lines = []
    dependencies: Lines = []
    escalation_policies: Lines = []
    approval_requirements: Lines = []
    success_metrics: Lines = []


class Reporting(BaseModel):
    cadence: Literal["daily", "weekly", "monthly"] = "daily"
    notes: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] = ""


class Operating(BaseModel):
    """SPEC step 5 operating modes. Monitoring (noticing events) is separate from execution (doing routine work):
    an event seen after hours waits for the execution window unless it is a critical alert."""

    mode: Literal["always_on", "business_hours", "scheduled", "event_driven", "on_demand"]
    monitoring: Literal["continuous", "business_hours", "off"] = "business_hours"
    execution_window: Literal["business_hours", "any_time"] = "business_hours"
    critical_alerts: Literal["immediate", "next_business_day"] = "immediate"


class KnowledgeAccess(BaseModel):
    doc_types: Annotated[list[DocType], Field(max_length=12)] = []
    access_levels: Annotated[list[Literal["general", "restricted", "confidential"]],
                             Field(min_length=1, max_length=3)] = ["general"]


class ModelConfig(BaseModel):
    tier: Literal["reasoning", "fast"] = "reasoning"
    effort: Literal["low", "medium", "high"] = "medium"


class Limits(BaseModel):
    monthly_budget_usd: Annotated[Decimal, Field(ge=0, le=100_000, decimal_places=2)]
    max_runs_per_day: Annotated[int, Field(ge=1, le=1000)] = 50


class AgentConfig(BaseModel):
    job: JobDescription
    reporting: Reporting
    operating: Operating
    permissions: dict[Scope, Literal["denied", "approval_required", "auto"]]
    knowledge: KnowledgeAccess
    model: ModelConfig
    limits: Limits
    automation_level: Literal["observe", "draft", "assisted", "autonomous"]

    @field_validator("permissions")
    @classmethod
    def _all_scopes(cls, v: dict[str, str]) -> dict[str, str]:
        # Every scope is explicit; anything not mentioned is denied.
        return {s: v.get(s, "denied") for s in policy.SCOPES}


class DraftIn(BaseModel):
    config: AgentConfig
    tasks: Annotated[list[TaskIn], Field(max_length=30)]


# ---- API ---------------------------------------------------------------------------------------------------------

class Issue(BaseModel):
    severity: Literal["error", "warning"]
    field: str
    message: str


class DefinitionOut(BaseModel):
    id: uuid.UUID
    key: str
    version: int
    letter: str
    name: str
    title: str
    department: str
    expertise: list[str]
    role_description: str
    responsibilities: list[str]
    prohibited: list[str]
    required_knowledge: list[str]
    data_sources: list[str]
    tools: list[dict[str, Any]]
    permission_ceilings: dict[str, str]
    escalation_conditions: list[str]
    kpis: list[dict[str, Any]]
    reporting_frequency: str
    default_operating_mode: str
    default_automation: str
    model: dict[str, Any]
    default_monthly_budget_usd: Decimal
    supported_events: list[str]
    task_templates: list[dict[str, Any]]
    # this workspace's live hire of the definition, if any ("available" when none)
    status: str = "available"
    instance_id: uuid.UUID | None = None


class RecommendationItem(BaseModel):
    key: str
    name: str
    letter: str
    score: int
    recommended: bool
    reasons: list[str]
    excluded_reason: str | None
    estimated_monthly_usd: Decimal
    hired: bool


class RecommendationOut(BaseModel):
    items: list[RecommendationItem]
    recommended_keys: list[str]
    total_estimated_monthly_usd: Decimal
    budget: dict[str, Any]  # {amount, currency, status: within|over|not_set|not_comparable, message}
    profile_gaps: list[str]
    method: str


class HireIn(BaseModel):
    definition_keys: Annotated[list[str], Field(min_length=1, max_length=8)]
    source: Literal["recommended", "custom"] = "custom"


class TaskOut(ORM):
    id: uuid.UUID
    key: str
    position: int
    title: str
    description: str
    trigger_type: str
    schedule: dict[str, Any] | None
    event: str | None
    inputs: list[str]
    actions: list[str]
    expected_output: str
    completion_criteria: list[str]
    priority: str
    sla_minutes: int | None
    policy_refs: list[str]
    required_permissions: list[str]
    approval_required: bool
    approval_reason: str | None
    failure: dict[str, Any]
    depends_on: list[str] = []


class ConfigSummaryOut(ORM):
    id: uuid.UUID
    instance_id: uuid.UUID
    version: int
    status: str
    config_hash: str
    source: str
    created_at: datetime
    submitted_at: datetime | None
    decided_at: datetime | None


class ConfigOut(ConfigSummaryOut):
    config: dict[str, Any]
    generation: dict[str, Any]
    tasks: list[TaskOut]
    issues: list[Issue]


class InstanceOut(ORM):
    id: uuid.UUID
    definition_key: str
    name: str
    status: str
    status_reason: str | None
    status_changed_at: datetime
    current_config_id: uuid.UUID | None
    approved_config_id: uuid.UUID | None
    deployment_stage: str | None
    activated_at: datetime | None
    created_at: datetime


class InstanceListItem(InstanceOut):
    letter: str
    department: str
    current_version: int | None = None
    current_config_status: str | None = None
    task_count: int = 0
    monthly_budget_usd: Decimal | None = None


class ApprovalOut(ORM):
    id: uuid.UUID
    subject_type: str
    subject_id: uuid.UUID
    instance_id: uuid.UUID | None
    subject_version: int | None
    subject_hash: str
    policy_version: str
    decision: str
    note: str | None
    scope: dict[str, Any]
    decided_by_id: uuid.UUID | None
    decided_by_name: str | None = None
    decided_by_role: str
    created_at: datetime


class InstanceDetailOut(InstanceOut):
    definition: DefinitionOut
    current_config: ConfigOut | None
    approvals: list[ApprovalOut]
    execution: dict[str, Any]  # {allowed, reason} — the guard Phase 5 tools will call


class SchedulePreviewOut(BaseModel):
    timezone: str | None
    execution_window: str
    tasks: list[dict[str, Any]]
    notes: list[str]
