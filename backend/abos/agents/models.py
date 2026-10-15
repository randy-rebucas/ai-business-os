"""AI workforce (SPEC §3 steps 2, 4, 5): catalog definitions, hired instances, versioned configurations, tasks.

`agent_definitions` is the platform catalog (no tenant; read-only to the app role). Everything else is tenant data
with RLS. A configuration is a draft until submitted; submitted, approved and rejected versions are frozen — an edit
creates the next version — so an approval's config hash always describes exactly what the CEO saw (ADR-018).
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from abos.core.db import Base, IdMixin, TenantMixin, TimestampMixin

LIFECYCLE = ("selected", "configuring", "awaiting_approval", "testing", "ready_for_deployment", "active", "paused",
             "failed", "retired")  # "available" = a catalog definition with no live instance
CONFIG_STATUSES = ("draft", "submitted", "approved", "rejected", "withdrawn")  # withdrawn: replaced before a decision


class AgentDefinition(IdMixin, Base):
    __tablename__ = "agent_definitions"
    __table_args__ = (UniqueConstraint("key", "version", name="uq_agent_definition_key_version"),)

    key: Mapped[str] = mapped_column(String(40))
    version: Mapped[int] = mapped_column(Integer)
    letter: Mapped[str] = mapped_column(String(2))
    name: Mapped[str] = mapped_column(String(120))
    department: Mapped[str] = mapped_column(String(120))
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    spec: Mapped[dict[str, Any]] = mapped_column(JSONB)  # the full catalog entry (catalog_v1.DEFINITIONS item)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AgentInstance(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "agent_instances"
    __table_args__ = (
        # One live hire per catalog agent per workspace; a retired one can be hired again.
        Index("uq_agent_instance_live", "organization_id", "definition_key", unique=True,
              postgresql_where=text("status <> 'retired'")),
    )

    definition_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_definitions.id", ondelete="RESTRICT"))
    definition_key: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(30), default="selected")
    status_reason: Mapped[str | None] = mapped_column(String(300))
    status_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    current_config_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_configurations.id", ondelete="SET NULL", use_alter=True))
    approved_config_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_configurations.id", ondelete="SET NULL", use_alter=True))
    hired_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    # observation: read + drafts only, whatever the configuration allows · full: the approved permissions apply.
    # Set on activation (always observation first) and widened only by a recorded CEO approval (SPEC step 6).
    deployment_stage: Mapped[str | None] = mapped_column(String(20))
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AgentConfiguration(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "agent_configurations"
    __table_args__ = (UniqueConstraint("instance_id", "version", name="uq_agent_configuration_version"),)

    instance_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_instances.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    config: Mapped[dict[str, Any]] = mapped_column(JSONB)  # validated by schemas.AgentConfig before storage
    config_hash: Mapped[str] = mapped_column(String(64))  # sha256 of config + tasks (canonical JSON)
    source: Mapped[str] = mapped_column(String(20))  # template | generated | edited
    # provider, model, dev label, evidence chunk ids, rules used, open questions, adjustments, warnings
    generation: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    submitted_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TaskDefinition(IdMixin, TenantMixin, Base):
    """A proposed task, versioned with its configuration (SPEC step 4 'Task and workflow generation')."""

    __tablename__ = "task_definitions"
    __table_args__ = (UniqueConstraint("configuration_id", "key", name="uq_task_definition_config_key"),)

    configuration_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_configurations.id", ondelete="CASCADE"), index=True)
    instance_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_instances.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(60))
    position: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    trigger_type: Mapped[str] = mapped_column(String(20))  # schedule | event | on_demand
    schedule: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    event: Mapped[str | None] = mapped_column(String(60))
    inputs: Mapped[list[str]] = mapped_column(JSONB, default=list)
    actions: Mapped[list[str]] = mapped_column(JSONB, default=list)
    expected_output: Mapped[str] = mapped_column(Text)
    completion_criteria: Mapped[list[str]] = mapped_column(JSONB, default=list)
    priority: Mapped[str] = mapped_column(String(10), default="normal")
    sla_minutes: Mapped[int | None] = mapped_column(Integer)
    policy_refs: Mapped[list[str]] = mapped_column(JSONB, default=list)  # business_rules ids
    required_permissions: Mapped[list[str]] = mapped_column(JSONB, default=list)
    approval_required: Mapped[bool] = mapped_column(Boolean, default=False)
    approval_reason: Mapped[str | None] = mapped_column(Text)
    failure: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TaskDependency(IdMixin, TenantMixin, Base):
    __tablename__ = "task_dependencies"
    __table_args__ = (UniqueConstraint("task_id", "depends_on_id", name="uq_task_dependency_pair"),)

    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("task_definitions.id", ondelete="CASCADE"), index=True)
    depends_on_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("task_definitions.id", ondelete="CASCADE"))
