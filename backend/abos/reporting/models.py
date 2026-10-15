"""Daily agent reports (SPEC §3 step 8). Built only from execution records — never from a model's recollection.

One report per agent per company-local day. `content` holds the 15 SPEC sections, each item carrying the ids of the
runs / executions / action requests it was derived from; `report_evidence` indexes those references so evidence can
be traced both ways. A report can be rebuilt (e.g. after a late approval decision changed a run's outcome): the
version increments, the content is replaced, and `final` says whether the reporting day had ended when it was built.
"""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from abos.core.db import Base, IdMixin, TenantMixin, TimestampMixin


class DailyReport(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "daily_reports"
    __table_args__ = (UniqueConstraint("instance_id", "report_date", name="uq_daily_report_agent_day"),
                      Index("ix_daily_reports_org_date", "organization_id", "report_date"))

    instance_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_instances.id", ondelete="CASCADE"))
    report_date: Mapped[date] = mapped_column(Date)  # company-local calendar day
    timezone: Mapped[str] = mapped_column(String(64))
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    final: Mapped[bool] = mapped_column(Boolean, default=False)  # the day had ended when this version was built
    version: Mapped[int] = mapped_column(Integer, default=1)
    summary: Mapped[str] = mapped_column(String(1000))
    counts: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)  # headline numbers for lists and the dashboard
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)  # the 15 sections
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ReportEvidence(IdMixin, TenantMixin, Base):
    __tablename__ = "report_evidence"
    __table_args__ = (Index("ix_report_evidence_ref", "ref_type", "ref_id"),)

    report_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("daily_reports.id", ondelete="CASCADE"), index=True)
    section: Mapped[str] = mapped_column(String(40))
    ref_type: Mapped[str] = mapped_column(String(30))  # workflow_run | tool_execution | action_request
    ref_id: Mapped[uuid.UUID] = mapped_column()
