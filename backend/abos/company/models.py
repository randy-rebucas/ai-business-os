"""Company profile (SPEC §3 step 1). One `company_profiles` row per organization plus typed child tables (ADR-005)."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from abos.core.db import Base, IdMixin, TenantMixin, TimestampMixin


class CompanyProfile(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "company_profiles"
    __table_args__ = (UniqueConstraint("organization_id", name="uq_company_profile_org"),)

    company_name: Mapped[str] = mapped_column(String(200))
    legal_name: Mapped[str | None] = mapped_column(String(200))
    trading_name: Mapped[str | None] = mapped_column(String(200))
    industry: Mapped[str | None] = mapped_column(String(120))
    business_category: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    target_customers: Mapped[str | None] = mapped_column(Text)
    company_size: Mapped[str | None] = mapped_column(String(20))  # see schemas.CompanySize
    employee_count: Mapped[int | None] = mapped_column(Integer)
    organization_structure: Mapped[str | None] = mapped_column(Text)
    timezone: Mapped[str | None] = mapped_column(String(64))  # IANA name, validated on write
    # {"mon": {"open": "09:00", "close": "17:00"} | null, ...}  — validated by schemas.OperatingSchedule
    operating_schedule: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    holidays: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)  # [{"date": "2026-12-25", "name": …}]
    reporting_cadence: Mapped[str | None] = mapped_column(String(20))  # daily | weekly | monthly
    notification_channels: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)  # {"in_app": true, ...}
    monthly_ai_budget: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    budget_currency: Mapped[str] = mapped_column(String(3), default="USD")
    # Sections the CEO chose to skip for now (shown as "skipped", still reported as missing context).
    skipped_sections: Mapped[list[str]] = mapped_column(JSONB, default=list)
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CompanyLocation(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "company_locations"

    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(30), default="office")  # headquarters | branch | office | store | …
    address: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(120))
    country: Mapped[str | None] = mapped_column(String(120))
    timezone: Mapped[str | None] = mapped_column(String(64))  # overrides the company timezone when set
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)


class Department(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "departments"
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_department_org_name"),)

    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    head_name: Mapped[str | None] = mapped_column(String(200))


class JobRole(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "job_roles"

    title: Mapped[str] = mapped_column(String(160))
    department_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("departments.id", ondelete="SET NULL"))
    description: Mapped[str | None] = mapped_column(Text)
    headcount: Mapped[int | None] = mapped_column(Integer)


class Offering(IdMixin, TimestampMixin, TenantMixin, Base):
    """A product or service the company sells."""

    __tablename__ = "company_offerings"

    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(20), default="product")  # product | service
    description: Mapped[str | None] = mapped_column(Text)
    sku: Mapped[str | None] = mapped_column(String(80))
    # Free-text pricing note as the CEO describes it. Authoritative price lists arrive as documents (Phase 2).
    pricing_note: Mapped[str | None] = mapped_column(String(300))


class BusinessObjective(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "business_objectives"

    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    kpi_name: Mapped[str | None] = mapped_column(String(160))
    kpi_target: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    kpi_unit: Mapped[str | None] = mapped_column(String(40))
    target_date: Mapped[date | None] = mapped_column(Date)
    department_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("departments.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | achieved | dropped


class BusinessProcess(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "business_processes"

    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    department_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("departments.id", ondelete="SET NULL"))
    frequency: Mapped[str | None] = mapped_column(String(40))
    approval_procedure: Mapped[str | None] = mapped_column(Text)


class SoftwareSystem(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "software_systems"

    name: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(40), default="other")  # accounting | crm | erp | …
    notes: Mapped[str | None] = mapped_column(Text)
    integration_wanted: Mapped[bool] = mapped_column(Boolean, default=False)


class OperationalChallenge(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "operational_challenges"

    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(10), default="medium")  # low | medium | high
    department_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("departments.id", ondelete="SET NULL"))
