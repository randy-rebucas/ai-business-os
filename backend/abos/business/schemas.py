import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, model_validator

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
Currency = Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"^[A-Z]{3}$")]
Amount = Annotated[Decimal, Field(gt=0, le=Decimal("999999999999.99"), decimal_places=2)]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class LineIn(BaseModel):
    description: Text
    quantity: Annotated[Decimal, Field(gt=0, le=1_000_000, decimal_places=4)] = Decimal(1)
    unit_price: Annotated[Decimal, Field(ge=0, le=Decimal("999999999999.99"), decimal_places=2)]


class InvoiceIn(BaseModel):
    number: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
    customer_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    customer_email: EmailStr | None = None
    currency: Currency
    issue_date: date
    due_date: date
    lines: Annotated[list[LineIn], Field(min_length=1, max_length=100)]
    recorded_total: Annotated[Decimal, Field(ge=0, decimal_places=2)] | None = None
    notes: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] | None = None
    source: Literal["manual", "import"] = "manual"

    @model_validator(mode="after")
    def _dates(self) -> "InvoiceIn":
        if self.due_date < self.issue_date:
            raise ValueError("The due date can't be before the issue date")
        return self


class PaymentIn(BaseModel):
    amount: Amount
    received_on: date
    method: Literal["bank_transfer", "card", "cash", "check", "other"] = "bank_transfer"
    reference: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)] | None = None


class ExpenseIn(BaseModel):
    incurred_on: date
    supplier: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    description: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    amount: Amount
    currency: Currency


class LineOut(ORM):
    id: uuid.UUID
    position: int
    description: str
    quantity: Decimal
    unit_price: Decimal
    amount: Decimal


class PaymentOut(ORM):
    id: uuid.UUID
    amount: Decimal
    currency: str
    received_on: date
    method: str
    reference: str | None
    created_at: datetime


class InvoiceOut(BaseModel):
    id: uuid.UUID
    number: str
    customer_name: str
    customer_email: str | None
    currency: str
    issue_date: date
    due_date: date
    total: Decimal
    recorded_total: Decimal | None
    paid: Decimal
    balance: Decimal
    state: Literal["open", "overdue", "paid", "void"]
    days_overdue: int
    aging: str
    checks: list[str]  # validated discrepancies (lines vs total, payments vs balance)
    notes: str | None
    source: str
    created_at: datetime
    lines: list[LineOut] = []
    payments: list[PaymentOut] = []


class ExpenseOut(ORM):
    id: uuid.UUID
    incurred_on: date
    supplier: str
    description: str
    amount: Decimal
    currency: str
    category: str | None
    status: str
    created_at: datetime


class DraftOut(ORM):
    id: uuid.UUID
    kind: str
    subject: str
    body: str
    recipient: str | None
    related_type: str | None
    related_id: uuid.UUID | None
    status: str
    instance_id: uuid.UUID | None
    run_id: uuid.UUID | None
    created_at: datetime
    sent_at: datetime | None


class ReceivablesOut(BaseModel):
    as_of: date
    outstanding_by_currency: dict[str, str]
    overdue_by_currency: dict[str, str]
    counts: dict[str, int]
