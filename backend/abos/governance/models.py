"""Governance (SPEC §3 steps 4–5, §6): business rules with their evidence, and the approval decision ledger."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from abos.core.db import Base, IdMixin, TenantMixin, TimestampMixin

# fact: stated in a source, quoted verbatim · proposed: an interpretation that would change agent behaviour ·
# unresolved: a question the sources don't answer · conflicting: sources disagree · confirmed / rejected: reviewed.
# Only `confirmed` rules are ever used as rules (ADR-017).
RULE_STATUSES = ("fact", "proposed", "unresolved", "conflicting", "confirmed", "rejected")
RULE_KINDS = ("policy", "workflow", "responsibility", "approval", "threshold", "customer_service", "operating_hours",
              "escalation", "reporting", "objective", "recurring", "dependency")


class BusinessRule(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "business_rules"
    __table_args__ = (
        UniqueConstraint("organization_id", "dedupe_key", name="uq_business_rule_org_key"),
        Index("ix_business_rules_org_status", "organization_id", "status"),
    )

    dedupe_key: Mapped[str] = mapped_column(String(80))  # re-extraction never duplicates or resets a review
    kind: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(300))
    statement: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(20))  # document | interview | profile | manual
    # [{chunk_id, document_id, document_title, version_no, section, quote}] — verified against the source text
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    source_ref: Mapped[str | None] = mapped_column(String(200))  # e.g. interview question id or profile field
    access_level: Mapped[str] = mapped_column(String(20), default="general")  # highest level among cited documents
    applies_to: Mapped[list[str]] = mapped_column(JSONB, default=list)  # agent definition keys; [] = all agents
    # Parsed deterministically from the quoted text, never taken from a model (SPEC §2).
    threshold_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    threshold_currency: Mapped[str | None] = mapped_column(String(3))
    conflicts_with: Mapped[list[str]] = mapped_column(JSONB, default=list)  # other rule ids
    resolution: Mapped[str | None] = mapped_column(Text)  # the CEO's answer / chosen version when confirming
    provider: Mapped[str] = mapped_column(String(30), default="rule")
    label: Mapped[str | None] = mapped_column(String(200))  # dev-adapter label when a dev adapter produced it
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class Approval(IdMixin, TenantMixin, Base):
    """One recorded decision (insert-only for the app role). Bound to the exact configuration hash and the policy
    version in force, so a later change to either is detectable (SPEC §6 'Human approval')."""

    __tablename__ = "approvals"
    __table_args__ = (Index("ix_approvals_org_created", "organization_id", "created_at"),)

    # agent_configuration | activation | deployment_stage | tool_action (subject = action_requests.id)
    subject_type: Mapped[str] = mapped_column(String(40))
    subject_id: Mapped[uuid.UUID] = mapped_column(index=True)
    instance_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("agent_instances.id", ondelete="CASCADE"))
    subject_version: Mapped[int | None] = mapped_column(Integer)
    subject_hash: Mapped[str] = mapped_column(String(64))
    policy_version: Mapped[str] = mapped_column(String(80))
    decision: Mapped[str] = mapped_column(String(20))  # approved | rejected
    note: Mapped[str | None] = mapped_column(Text)
    scope: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)  # what exactly was authorised
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    decided_by_role: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ActionRequest(IdMixin, TimestampMixin, TenantMixin, Base):
    """A held tool call waiting for a person (SPEC §6 'Human approval'). Bound to the exact parameters, the agent's
    configuration hash and the policy version via `params_hash`; if any of them differs when the run resumes, the
    request is superseded and a new one is raised. Decisions are also written to the insert-only `approvals` ledger
    (subject_type `tool_action`)."""

    __tablename__ = "action_requests"
    __table_args__ = (Index("ix_action_requests_org_status", "organization_id", "status"),)

    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflow_runs.id", ondelete="CASCADE"), index=True)
    instance_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_instances.id", ondelete="CASCADE"))
    step_no: Mapped[int] = mapped_column(Integer)
    tool: Mapped[str] = mapped_column(String(60))
    tool_label: Mapped[str] = mapped_column(String(200))
    scope: Mapped[str | None] = mapped_column(String(40))
    risk: Mapped[str] = mapped_column(String(10))
    input: Mapped[dict[str, Any]] = mapped_column(JSONB)  # the call as planned
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB)  # the exact action resolved for the approver
    params_hash: Mapped[str] = mapped_column(String(64))
    config_hash: Mapped[str] = mapped_column(String(64))
    policy_version: Mapped[str] = mapped_column(String(80))
    reason: Mapped[str] = mapped_column(String(500))  # why the dispatcher held it
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|approved|rejected|superseded|used|cancelled
    note: Mapped[str | None] = mapped_column(Text)
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    decided_by_role: Mapped[str | None] = mapped_column(String(20))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approval_id: Mapped[uuid.UUID | None] = mapped_column()
