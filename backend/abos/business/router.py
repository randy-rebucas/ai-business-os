import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Body, Depends, Query
from pydantic import StringConstraints
from sqlalchemy.orm import Session

from abos.business import schemas as s
from abos.business import service
from abos.core.db import get_db
from abos.identity.deps import OrgContext, require_org_permission

router = APIRouter(prefix="/api/v1/business", tags=["business records"])

READ = require_org_permission("records.read")
MANAGE = require_org_permission("records.manage")


@router.get("/invoices", response_model=list[s.InvoiceOut])
def invoices(state: Literal["all", "outstanding", "overdue", "paid", "void"] = "all",
             ctx: OrgContext = Depends(READ), db: Session = Depends(get_db)):
    return service.query_invoices(db, ctx.org_id, state=state)


@router.get("/receivables", response_model=s.ReceivablesOut)
def receivables(ctx: OrgContext = Depends(READ), db: Session = Depends(get_db)):
    return service.receivables(db, ctx.org_id)


@router.post("/invoices", response_model=s.InvoiceOut, status_code=201)
def create_invoice(data: s.InvoiceIn, ctx: OrgContext = Depends(MANAGE), db: Session = Depends(get_db)):
    return service.invoice_out(db, service.create_invoice(db, ctx, data))


@router.get("/invoices/{invoice_id}", response_model=s.InvoiceOut)
def invoice(invoice_id: uuid.UUID, ctx: OrgContext = Depends(READ), db: Session = Depends(get_db)):
    return service.invoice_out(db, service.get_invoice(db, ctx, invoice_id))


@router.post("/invoices/{invoice_id}/payments", response_model=s.InvoiceOut, status_code=201)
def record_payment(invoice_id: uuid.UUID, data: s.PaymentIn, ctx: OrgContext = Depends(MANAGE),
                   db: Session = Depends(get_db)):
    service.record_payment(db, ctx, invoice_id, data)
    return service.invoice_out(db, service.get_invoice(db, ctx, invoice_id))


@router.post("/invoices/{invoice_id}/void", response_model=s.InvoiceOut)
def void_invoice(invoice_id: uuid.UUID,
                 reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300),
                                   Body(embed=True)],
                 ctx: OrgContext = Depends(MANAGE), db: Session = Depends(get_db)):
    return service.invoice_out(db, service.void_invoice(db, ctx, invoice_id, reason))


@router.get("/expenses", response_model=list[s.ExpenseOut])
def expenses(ctx: OrgContext = Depends(READ), db: Session = Depends(get_db)):
    return service.query_expenses(db, ctx.org_id)


@router.post("/expenses", response_model=s.ExpenseOut, status_code=201)
def create_expense(data: s.ExpenseIn, ctx: OrgContext = Depends(MANAGE), db: Session = Depends(get_db)):
    return service.create_expense(db, ctx, data)


@router.get("/drafts", response_model=list[s.DraftOut])
def drafts(status: Literal["draft", "sent", "discarded"] | None = None, limit: int = Query(100, ge=1, le=200),
           ctx: OrgContext = Depends(READ), db: Session = Depends(get_db)):
    return service.list_drafts(db, ctx.org_id, status, limit)


@router.post("/drafts/{draft_id}/discard", response_model=s.DraftOut)
def discard_draft(draft_id: uuid.UUID, ctx: OrgContext = Depends(MANAGE), db: Session = Depends(get_db)):
    return service.discard_draft(db, ctx, draft_id)
