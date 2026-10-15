"""Authoritative business records the first real tools act on (SPEC §2 'business systems', ARCHITECTURE §1).

Invoices, their lines and payments, expenses, and the drafts agents prepare. People enter records through validated
business APIs; agents read them through registered tools and may only create drafts. Money is `Numeric(18, 2)` and
every derived figure (totals, balances, days overdue) is computed by `calculations.py`, never stored from a model.
Invoice lines and payments are insert-only for the app role: a correction is a new record, not an edit.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from abos.core.db import Base, IdMixin, TenantMixin, TimestampMixin


class Invoice(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("organization_id", "number", name="uq_invoice_org_number"),
        CheckConstraint("total >= 0", name="total_not_negative"),
        CheckConstraint("due_date >= issue_date", name="due_after_issue"),
        Index("ix_invoices_org_due", "organization_id", "due_date"),
    )

    number: Mapped[str] = mapped_column(String(40))
    customer_name: Mapped[str] = mapped_column(String(200))
    customer_email: Mapped[str | None] = mapped_column(String(254))
    currency: Mapped[str] = mapped_column(String(3))
    issue_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date] = mapped_column(Date)
    total: Mapped[Decimal] = mapped_column(Numeric(18, 2))  # computed from the lines when the invoice is recorded
    # The total as stated by the source system, when it was imported; a mismatch is a discrepancy to escalate.
    recorded_total: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    status: Mapped[str] = mapped_column(String(20), default="issued")  # issued | void (paid/overdue are derived)
    notes: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual | import
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InvoiceLine(IdMixin, TenantMixin, Base):
    __tablename__ = "invoice_lines"
    __table_args__ = (CheckConstraint("quantity > 0", name="quantity_positive"),)

    invoice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(String(300))
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))  # quantity × unit price, rounded half-up to cents


class Payment(IdMixin, TenantMixin, Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        # The same bank reference can't be recorded twice for one invoice (double-entry guard).
        Index("uq_payment_invoice_reference", "invoice_id", "reference", unique=True,
              postgresql_where=text("reference IS NOT NULL")),
    )

    invoice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(3))
    received_on: Mapped[date] = mapped_column(Date)
    method: Mapped[str] = mapped_column(String(30))
    reference: Mapped[str | None] = mapped_column(String(100))
    recorded_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Expense(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "expenses"
    __table_args__ = (CheckConstraint("amount > 0", name="amount_positive"),)

    incurred_on: Mapped[date] = mapped_column(Date)
    supplier: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(500))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(3))
    category: Mapped[str | None] = mapped_column(String(60))  # set by a person; agents only propose
    status: Mapped[str] = mapped_column(String(20), default="submitted")  # submitted | approved | rejected
    submitted_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class Draft(IdMixin, TimestampMixin, TenantMixin, Base):
    """Something an agent prepared for a person: a payment reminder, a briefing. Never sent by being drafted."""

    __tablename__ = "drafts"
    __table_args__ = (Index("ix_drafts_org_created", "organization_id", "created_at"),)

    kind: Mapped[str] = mapped_column(String(30))  # payment_reminder | briefing
    subject: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    recipient: Mapped[str | None] = mapped_column(String(254))
    related_type: Mapped[str | None] = mapped_column(String(30))  # invoice | …
    related_id: Mapped[uuid.UUID | None] = mapped_column()
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | sent | discarded
    instance_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("agent_instances.id", ondelete="SET NULL"))
    run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workflow_runs.id", ondelete="SET NULL"))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
