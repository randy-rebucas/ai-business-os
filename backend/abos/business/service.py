"""Business records service: validated APIs for people, read/draft functions for agent tools (SPEC §6 'Financial
safety'). Totals, balances and overdue days always come from `calculations`; a payment can't exceed the balance or
change currency, and is recorded under a row lock so two concurrent payments can't both pass the check.
Recording a record emits its business event (`invoice.created`, `payment.received`, `expense.submitted`), which
starts the event-driven tasks of active agents.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from abos.audit import service as audit
from abos.business import calculations as calc
from abos.business import schemas as s
from abos.business.models import Draft, Expense, Invoice, InvoiceLine, Payment
from abos.company import service as company
from abos.core.errors import AppError, conflict, not_found
from abos.identity.deps import OrgContext
from abos.orchestration import events

MAX_LIST = 500


def company_today(db: Session, org_id: uuid.UUID) -> date:
    """Today in the company's time zone (UTC until one is set) — overdue means overdue where the company is."""
    tz = company.get_profile(db, org_id).timezone
    return datetime.now(ZoneInfo(tz) if tz else UTC).date()


# ---- invoices ----------------------------------------------------------------------------------------------------

def _lines(db: Session, invoice_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[InvoiceLine]]:
    out: dict[uuid.UUID, list[InvoiceLine]] = {i: [] for i in invoice_ids}
    for line in db.scalars(select(InvoiceLine).where(InvoiceLine.invoice_id.in_(invoice_ids))
                           .order_by(InvoiceLine.position)):
        out[line.invoice_id].append(line)
    return out


def _payments(db: Session, invoice_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[Payment]]:
    out: dict[uuid.UUID, list[Payment]] = {i: [] for i in invoice_ids}
    for p in db.scalars(select(Payment).where(Payment.invoice_id.in_(invoice_ids)).order_by(Payment.received_on)):
        out[p.invoice_id].append(p)
    return out


def view(inv: Invoice, lines: list[InvoiceLine], payments: list[Payment], today: date) -> dict:
    """The invoice with every derived figure, as plain JSON (what the API shows and what tools return)."""
    paid = calc.money(sum((p.amount for p in payments), Decimal(0)))
    balance = calc.money(inv.total - paid)
    void = inv.status == "void"
    days = 0 if void else calc.days_overdue(inv.due_date, today, balance)
    state = "void" if void else "paid" if balance <= 0 else "overdue" if days > 0 else "open"
    # The balance is always total − payments here (payments are validated on entry), so the check that can fail is
    # an imported invoice whose stated total disagrees with its own lines.
    stated = inv.recorded_total if inv.recorded_total is not None else inv.total
    checks = calc.invoice_checks({"number": inv.number, "total": str(stated),
                                  "lines": [{"amount": str(x.amount)} for x in lines]})
    return {
        "id": str(inv.id), "number": inv.number, "customer_name": inv.customer_name,
        "customer_email": inv.customer_email, "currency": inv.currency, "issue_date": inv.issue_date.isoformat(),
        "due_date": inv.due_date.isoformat(), "total": str(inv.total),
        "recorded_total": str(inv.recorded_total) if inv.recorded_total is not None else None,
        "paid": str(paid), "balance": str(balance), "state": state, "days_overdue": days,
        "aging": calc.aging_bucket(days), "follow_up_priority": calc.follow_up_priority(days, balance),
        "checks": checks, "notes": inv.notes, "source": inv.source, "created_at": inv.created_at.isoformat(),
        "lines": [{"id": str(x.id), "position": x.position, "description": x.description, "quantity": str(x.quantity),
                   "unit_price": str(x.unit_price), "amount": str(x.amount)} for x in lines],
        "payments": [{"id": str(p.id), "amount": str(p.amount), "currency": p.currency,
                      "received_on": p.received_on.isoformat(), "method": p.method, "reference": p.reference,
                      "created_at": p.created_at.isoformat()} for p in payments],
    }


def views(db: Session, invoices: list[Invoice], today: date) -> list[dict]:
    ids = [i.id for i in invoices]
    lines, payments = _lines(db, ids), _payments(db, ids)
    return [view(i, lines[i.id], payments[i.id], today) for i in invoices]


def query_invoices(db: Session, org_id: uuid.UUID, *, state: str = "all", invoice_id: uuid.UUID | None = None,
                   number: str | None = None, period: str | None = None, today: date | None = None,
                   limit: int = MAX_LIST) -> list[dict]:
    """Invoice views for one organisation. state: all | outstanding (open + overdue) | overdue | paid | void.
    period: 'YYYY-MM' of the issue date."""
    today = today or company_today(db, org_id)
    stmt = select(Invoice).where(Invoice.organization_id == org_id)
    if invoice_id:
        stmt = stmt.where(Invoice.id == invoice_id)
    if number:
        stmt = stmt.where(Invoice.number == number)
    if period:
        y, m = (int(x) for x in period.split("-"))
        start = date(y, m, 1)
        stmt = stmt.where(Invoice.issue_date >= start, Invoice.issue_date < date(y + m // 12, m % 12 + 1, 1))
    rows = views(db, list(db.scalars(stmt.order_by(Invoice.due_date, Invoice.number).limit(MAX_LIST))), today)
    wanted = {"all": None, "outstanding": ("open", "overdue"), "overdue": ("overdue",), "paid": ("paid",),
              "void": ("void",)}[state]
    return [r for r in rows if wanted is None or r["state"] in wanted][:limit]


def get_invoice(db: Session, ctx: OrgContext, invoice_id: uuid.UUID) -> Invoice:
    inv = db.get(Invoice, invoice_id)
    if inv is None or inv.organization_id != ctx.org_id:
        raise not_found("Invoice")
    return inv


def invoice_out(db: Session, inv: Invoice) -> dict:
    return query_invoices(db, inv.organization_id, invoice_id=inv.id)[0]


def create_invoice(db: Session, ctx: OrgContext, data: s.InvoiceIn) -> Invoice:
    amounts = [calc.line_amount(x.quantity, x.unit_price) for x in data.lines]
    inv = Invoice(organization_id=ctx.org_id, number=data.number, customer_name=data.customer_name,
                  customer_email=data.customer_email, currency=data.currency, issue_date=data.issue_date,
                  due_date=data.due_date, total=calc.money(sum(amounts, Decimal(0))),
                  recorded_total=data.recorded_total, notes=data.notes, source=data.source,
                  created_by_id=ctx.user.id)
    try:
        db.add(inv)
        db.flush()
        for i, (line, amount) in enumerate(zip(data.lines, amounts, strict=True)):
            db.add(InvoiceLine(organization_id=ctx.org_id, invoice_id=inv.id, position=i,
                               description=line.description, quantity=line.quantity, unit_price=line.unit_price,
                               amount=amount))
        audit.record(db, "business.invoice_created", actor_id=ctx.user.id, org_id=ctx.org_id, target_type="invoice",
                     target_id=inv.id, data={"number": inv.number, "total": str(inv.total),
                                             "currency": inv.currency}, ip=ctx.meta.ip)
        events.emit(db, ctx.org_id, "invoice.created", subject_type="invoice", subject_id=inv.id)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise conflict(f"Invoice {data.number} already exists") from exc
    db.refresh(inv)
    return inv


def record_payment(db: Session, ctx: OrgContext, invoice_id: uuid.UUID, data: s.PaymentIn) -> Payment:
    inv = db.scalar(select(Invoice).where(Invoice.id == invoice_id, Invoice.organization_id == ctx.org_id)
                    .with_for_update())
    if inv is None:
        raise not_found("Invoice")
    if inv.status == "void":
        raise AppError(409, "invoice_void", "Payments can't be recorded against a void invoice")
    paid = db.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.invoice_id == inv.id))
    balance = calc.money(inv.total - Decimal(str(paid)))
    if data.amount > balance:
        raise AppError(409, "overpayment", f"The payment of {data.amount} {inv.currency} is more than the balance of "
                                           f"{balance} {inv.currency}", {"balance": str(balance)})
    if data.received_on < inv.issue_date:
        raise AppError(422, "validation_error", "A payment can't be received before the invoice was issued")
    payment = Payment(organization_id=ctx.org_id, invoice_id=inv.id, amount=data.amount, currency=inv.currency,
                      received_on=data.received_on, method=data.method, reference=data.reference,
                      recorded_by_id=ctx.user.id)
    try:
        db.add(payment)
        db.flush()
        audit.record(db, "business.payment_recorded", actor_id=ctx.user.id, org_id=ctx.org_id,
                     target_type="invoice", target_id=inv.id,
                     data={"payment_id": str(payment.id), "amount": str(payment.amount), "currency": inv.currency},
                     ip=ctx.meta.ip)
        events.emit(db, ctx.org_id, "payment.received", subject_type="payment", subject_id=payment.id,
                    invoice_id=str(inv.id))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise conflict("A payment with this reference is already recorded for this invoice") from exc
    db.refresh(payment)
    return payment


def void_invoice(db: Session, ctx: OrgContext, invoice_id: uuid.UUID, reason: str) -> Invoice:
    inv = get_invoice(db, ctx, invoice_id)
    if inv.status == "void":
        raise conflict("This invoice is already void")
    if db.scalar(select(Payment.id).where(Payment.invoice_id == inv.id).limit(1)):
        raise AppError(409, "has_payments", "An invoice with recorded payments can't be voided")
    inv.status, inv.voided_at = "void", datetime.now(UTC)
    audit.record(db, "business.invoice_voided", actor_id=ctx.user.id, org_id=ctx.org_id, target_type="invoice",
                 target_id=inv.id, data={"reason": reason}, ip=ctx.meta.ip)
    db.commit()
    return inv


def receivables(db: Session, org_id: uuid.UUID) -> dict:
    today = company_today(db, org_id)
    rows = query_invoices(db, org_id, today=today)
    outstanding = [r for r in rows if r["state"] in ("open", "overdue")]
    return {"as_of": today, "outstanding_by_currency": calc.totals_by_currency(outstanding, "balance"),
            "overdue_by_currency": calc.totals_by_currency([r for r in outstanding if r["state"] == "overdue"],
                                                           "balance"),
            "counts": {k: sum(1 for r in rows if r["state"] == k) for k in ("open", "overdue", "paid", "void")}}


# ---- expenses ----------------------------------------------------------------------------------------------------

def expense_view(e: Expense) -> dict:
    return {"id": str(e.id), "incurred_on": e.incurred_on.isoformat(), "supplier": e.supplier,
            "description": e.description, "amount": str(e.amount), "currency": e.currency, "category": e.category,
            "status": e.status, "created_at": e.created_at.isoformat()}


def query_expenses(db: Session, org_id: uuid.UUID, *, expense_id: uuid.UUID | None = None,
                   status: str | None = None, period: str | None = None, limit: int = MAX_LIST) -> list[Expense]:
    stmt = select(Expense).where(Expense.organization_id == org_id)
    if expense_id:
        stmt = stmt.where(Expense.id == expense_id)
    if status:
        stmt = stmt.where(Expense.status == status)
    if period:
        y, m = (int(x) for x in period.split("-"))
        stmt = stmt.where(Expense.incurred_on >= date(y, m, 1),
                          Expense.incurred_on < date(y + m // 12, m % 12 + 1, 1))
    return list(db.scalars(stmt.order_by(Expense.incurred_on.desc(), Expense.created_at.desc()).limit(limit)))


def create_expense(db: Session, ctx: OrgContext, data: s.ExpenseIn) -> Expense:
    e = Expense(organization_id=ctx.org_id, incurred_on=data.incurred_on, supplier=data.supplier,
                description=data.description, amount=data.amount, currency=data.currency, submitted_by_id=ctx.user.id)
    db.add(e)
    db.flush()
    audit.record(db, "business.expense_submitted", actor_id=ctx.user.id, org_id=ctx.org_id, target_type="expense",
                 target_id=e.id, data={"amount": str(e.amount), "currency": e.currency}, ip=ctx.meta.ip)
    events.emit(db, ctx.org_id, "expense.submitted", subject_type="expense", subject_id=e.id)
    db.commit()
    db.refresh(e)
    return e


# ---- drafts ------------------------------------------------------------------------------------------------------

def create_draft(db: Session, org_id: uuid.UUID, *, kind: str, subject: str, body: str, recipient: str | None,
                 related_type: str | None, related_id: uuid.UUID | None, instance_id: uuid.UUID | None,
                 run_id: uuid.UUID | None) -> Draft:
    d = Draft(organization_id=org_id, kind=kind, subject=subject[:300], body=body, recipient=recipient,
              related_type=related_type, related_id=related_id, instance_id=instance_id, run_id=run_id)
    db.add(d)
    db.flush()
    return d


def list_drafts(db: Session, org_id: uuid.UUID, status: str | None = None, limit: int = 200) -> list[Draft]:
    stmt = select(Draft).where(Draft.organization_id == org_id)
    if status:
        stmt = stmt.where(Draft.status == status)
    return list(db.scalars(stmt.order_by(Draft.created_at.desc()).limit(limit)))


def discard_draft(db: Session, ctx: OrgContext, draft_id: uuid.UUID) -> Draft:
    d = db.get(Draft, draft_id)
    if d is None or d.organization_id != ctx.org_id:
        raise not_found("Draft")
    if d.status != "draft":
        raise conflict(f"This draft is already {d.status}")
    d.status = "discarded"
    audit.record(db, "business.draft_discarded", actor_id=ctx.user.id, org_id=ctx.org_id, target_type="draft",
                 target_id=d.id, ip=ctx.meta.ip)
    db.commit()
    return d
