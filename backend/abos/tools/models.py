"""The tool execution ledger: evidence for every call an agent's plan made (SPEC §3 step 7, step 8 'evidence').

One row per attempted call, whatever happened to it — executed, refused by governance, held for approval, rejected
as invalid, not connected, failed, or of unknown outcome. Write-once for the app role: a row is inserted with its
final status, except a non-transactional side effect, which is inserted as `started` before the call and completed
exactly once (DB trigger); DELETE is revoked. `idempotency_key` is unique per workspace for actions with effects, so
the same action for the same trigger can't run twice even across workers and retries.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from abos.core.db import Base, IdMixin, TenantMixin

# started (non-transactional side effect in flight) · succeeded · unverified (outcome unknown) · failed ·
# blocked / held / refused / rejected_input / unknown_tool / unavailable (never ran) · duplicate (suppressed) ·
# rejected (a person rejected the held action)
STATUSES = ("started", "succeeded", "unverified", "failed", "blocked", "held", "refused", "rejected_input",
            "unknown_tool", "unavailable", "duplicate", "rejected")
RAN = ("succeeded", "unverified", "failed")


class ToolExecution(IdMixin, TenantMixin, Base):
    __tablename__ = "tool_executions"
    __table_args__ = (
        Index("uq_tool_execution_idempotency", "organization_id", "idempotency_key", unique=True,
              postgresql_where=text("idempotency_key IS NOT NULL")),
        Index("ix_tool_executions_run", "run_id", "step_no"),
        Index("ix_tool_executions_instance", "instance_id", "created_at"),
        Index("ix_tool_executions_org_created", "organization_id", "created_at"),  # usage, reports, metrics
    )

    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflow_runs.id", ondelete="CASCADE"))
    instance_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_instances.id", ondelete="CASCADE"))
    step_no: Mapped[int] = mapped_column(Integer)
    tool: Mapped[str] = mapped_column(String(60))
    registry_version: Mapped[str] = mapped_column(String(40))
    scope: Mapped[str | None] = mapped_column(String(40))
    risk: Mapped[str] = mapped_column(String(10))
    input: Mapped[Any] = mapped_column(JSONB)  # exactly what the plan proposed (may be invalid)
    input_hash: Mapped[str] = mapped_column(String(64))
    idempotency_key: Mapped[str | None] = mapped_column(String(64))
    decision: Mapped[str] = mapped_column(String(30))  # the dispatcher's decision
    reason: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    output: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)  # [{type, id, label}]
    approval_request_id: Mapped[uuid.UUID | None] = mapped_column()
    error: Mapped[str | None] = mapped_column(String(500))
    planner: Mapped[str] = mapped_column(String(20))  # playbook | model
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExecutionReconciliation(IdMixin, TenantMixin, Base):
    """How an `unverified` outcome was later settled (insert-only). The ledger row stays as written; reports read
    the latest reconciliation to tell "attempted, outcome unknown" from "confirmed afterwards" (SPEC step 8)."""

    __tablename__ = "execution_reconciliations"
    __table_args__ = (Index("uq_execution_reconciliation", "execution_id", unique=True),)

    execution_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tool_executions.id", ondelete="CASCADE"))
    outcome: Mapped[str] = mapped_column(String(20))  # confirmed | failed
    source: Mapped[str] = mapped_column(String(40))  # email_outbox | …
    detail: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
