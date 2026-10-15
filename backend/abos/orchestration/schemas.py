import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RunIn(BaseModel):
    agent_id: uuid.UUID
    task_key: Annotated[str, StringConstraints(max_length=60)] | None = None
    request: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] | None = None

    @model_validator(mode="after")
    def _one(self) -> "RunIn":
        if not self.task_key and not self.request:
            raise ValueError("Choose a task or describe the request")
        return self


class RunOut(ORM):
    id: uuid.UUID
    instance_id: uuid.UUID
    agent_name: str | None = None
    definition_key: str | None = None
    configuration_id: uuid.UUID
    config_version: int
    config_hash: str
    policy_version: str
    task_key: str
    task_title: str
    trigger_type: str
    trigger: dict[str, Any]
    request: str | None
    parent_id: uuid.UUID | None
    depth: int
    status: str
    status_reason: str | None
    not_before: datetime | None
    planner: dict[str, Any]
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    summary: str = ""
    validation_passed: bool | None = None


class ExecutionOut(ORM):
    id: uuid.UUID
    run_id: uuid.UUID
    instance_id: uuid.UUID
    step_no: int
    tool: str
    registry_version: str
    scope: str | None
    risk: str
    input: Any
    input_hash: str
    idempotency_key: str | None
    decision: str
    reason: str
    status: str
    attempts: int
    output: dict[str, Any]
    evidence: list[dict[str, Any]]
    approval_request_id: uuid.UUID | None
    error: str | None
    planner: str
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int | None


class ActionRequestOut(BaseModel):
    id: uuid.UUID
    run_id: uuid.UUID
    instance_id: uuid.UUID
    agent_name: str | None
    task_title: str | None
    step_no: int
    tool: str
    tool_label: str
    scope: str | None
    risk: str
    parameters: dict[str, Any]
    params_hash: str
    config_hash: str
    policy_version: str
    reason: str
    status: str
    note: str | None
    decided_by_name: str | None
    decided_by_role: str | None
    decided_at: datetime | None
    created_at: datetime


class RunDetailOut(RunOut):
    steps: list[dict[str, Any]]
    output: dict[str, Any]
    validation: dict[str, Any]
    error: str | None
    executions: list[ExecutionOut]
    action_requests: list[ActionRequestOut]
    children: list[dict[str, Any]]
    parent: dict[str, Any] | None


class ActionDecisionIn(BaseModel):
    decision: Annotated[str, StringConstraints(pattern="^(approved|rejected)$")]
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] | None = None
    params_hash: Annotated[str, Field(min_length=64, max_length=64)]
