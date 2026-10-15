"""Workflow runs: one execution of one agent task (SPEC §3 step 7). See docs/EXECUTION.md.

A run is bound to the configuration version and hash it was created under; if the agent's approved configuration
changes before or during the run, the run stops (`blocked`). `idempotency_key` is unique per workspace — one run per
schedule occurrence, per event and subject, per explicit request key — so a re-delivered event or a scheduler that
ticks twice never starts the same work twice. Evidence lives in `tool_executions` (insert-only / write-once).
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from abos.core.db import Base, IdMixin, TenantMixin, TimestampMixin


class WorkflowRun(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "workflow_runs"
    __table_args__ = (
        UniqueConstraint("organization_id", "idempotency_key", name="uq_workflow_run_idempotency"),
        Index("ix_workflow_runs_instance", "instance_id", "created_at"),
        Index("ix_workflow_runs_org_status", "organization_id", "status"),
        Index("ix_workflow_runs_org_created", "organization_id", "created_at"),  # reports, usage, Control Center
    )

    instance_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_instances.id", ondelete="CASCADE"))
    configuration_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_configurations.id", ondelete="CASCADE"))
    config_version: Mapped[int] = mapped_column(Integer)
    config_hash: Mapped[str] = mapped_column(String(64))
    policy_version: Mapped[str] = mapped_column(String(80))
    task_key: Mapped[str] = mapped_column(String(60))  # a configured task, or "request" for an ad-hoc request
    task_title: Mapped[str] = mapped_column(String(200))
    trigger_type: Mapped[str] = mapped_column(String(20))  # schedule | event | on_demand | delegated
    # {occurrence} | {event, subject_type, subject_id} | {requested_by} | {parent_run_id}
    trigger: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    request: Mapped[str | None] = mapped_column(Text)  # the person's request, for ad-hoc and delegated runs
    idempotency_key: Mapped[str] = mapped_column(String(200))
    lock_key: Mapped[str] = mapped_column(String(200))  # runs with the same key never execute concurrently
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workflow_runs.id", ondelete="CASCADE"),
                                                        index=True)
    depth: Mapped[int] = mapped_column(Integer, default=0)  # 0 = top level, 1 = delegated (the maximum)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    status_reason: Mapped[str | None] = mapped_column(String(500))
    not_before: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # deferred to business hours
    planner: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)  # {mode, provider, model, label}
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)  # summary per step → execution ids
    output: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)  # {summary, findings, missing_evidence}
    validation: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)  # {passed, checks: [{label, ok, detail}]}
    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(String(500))
