"""Scenario simulation & readiness (SPEC §3 step 6). Scenarios, runs and per-scenario results with traces."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from abos.core.db import Base, IdMixin, TenantMixin, TimestampMixin

CATEGORIES = ("normal", "missing_information", "conflicting_policies", "outdated_documents", "unauthorized_request",
              "insufficient_permissions", "failed_integration", "transient_error", "duplicate_execution",
              "financial_discrepancy", "escalation", "malicious_document", "cross_tenant", "approval_required")


class SimulationScenario(IdMixin, TimestampMixin, TenantMixin, Base):
    """A test case for one catalog agent. Library scenarios are copied in per workspace (source=library) so they
    can be read, versioned and extended; custom ones are added by the workspace."""

    __tablename__ = "simulation_scenarios"
    __table_args__ = (UniqueConstraint("organization_id", "agent_key", "key", name="uq_scenario_org_agent_key"),)

    agent_key: Mapped[str] = mapped_column(String(40))
    key: Mapped[str] = mapped_column(String(80))
    version: Mapped[int] = mapped_column(Integer, default=1)
    category: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    # {request, actor, event?, task?}
    input: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    # {records: {tool_key: [..]}, documents: [{title, content, status, org, doc_type, access_level}], faults: {..}}
    fixtures: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    # the actions a naive or compromised agent attempts — used as the plan when no AI model is configured
    scripted_plan: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    assertions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)  # deterministic checks
    expected_outcome: Mapped[str] = mapped_column(Text)  # what should happen, in words
    required: Mapped[bool] = mapped_column(Boolean, default=True)  # part of the readiness suite
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[str] = mapped_column(String(10), default="library")  # library | custom


class SimulationRun(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "simulation_runs"
    __table_args__ = (Index("ix_simulation_runs_instance", "instance_id", "created_at"),)

    instance_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_instances.id", ondelete="CASCADE"))
    configuration_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_configurations.id", ondelete="CASCADE"))
    config_version: Mapped[int] = mapped_column(Integer)
    config_hash: Mapped[str] = mapped_column(String(64))
    policy_version: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued | running | completed | error
    passed: Mapped[bool | None] = mapped_column(Boolean)
    planner: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)  # {mode, provider, model, label}
    suite: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)  # [{scenario_id, key, version, required}]
    scores: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)  # dimension -> {passed, total, score}
    thresholds: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)  # counts, mandatory failures, gate reasons
    error: Mapped[str | None] = mapped_column(String(500))
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SimulationResult(IdMixin, TenantMixin, Base):
    __tablename__ = "simulation_results"

    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("simulation_runs.id", ondelete="CASCADE"), index=True)
    scenario_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("simulation_scenarios.id", ondelete="SET NULL"))
    scenario_key: Mapped[str] = mapped_column(String(80))
    scenario_version: Mapped[int] = mapped_column(Integer)
    category: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(200))
    passed: Mapped[bool] = mapped_column(Boolean)
    mandatory_failed: Mapped[bool] = mapped_column(Boolean, default=False)
    outcome: Mapped[str] = mapped_column(String(20))  # completed | escalated | incomplete
    trace: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)  # every attempted call + decision
    output: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)  # final answer + verified citations
    assertions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)  # each with passed + detail
    analysis: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)  # explanation + suggested changes
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
