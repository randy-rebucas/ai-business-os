"""Real tool implementations. Each acts only on the calling organisation's records through validated business APIs
(no SQL, shell or HTTP from a plan), returns structured output plus evidence references, and raises:

- `Refused`  — a validation rule says no (e.g. reminding a customer about a paid invoice); nothing happened.
- `Transient` — a timeout or connection fault; nothing happened, the call may be retried if the tool is idempotent.
Any other exception is a failure. Money figures are strings produced by `business.calculations`.
"""

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from abos.agents.models import AgentInstance
from abos.audit import service as audit
from abos.business import calculations as calc
from abos.business import service as business
from abos.business.models import Draft
from abos.company.models import BusinessObjective
from abos.core.config import get_settings
from abos.governance.dispatch import Threshold
from abos.identity import mailer
from abos.knowledge import retrieval, safety
from abos.llm import gateway
from abos.notifications import service as notifications

REMINDER_GAP_DAYS = 7  # at most one payment reminder per invoice per week (platform rule)


class Refused(Exception):
    """A tool's validation rule rejected the call; nothing was changed."""


class Transient(Exception):
    """Timed out or couldn't connect; nothing was changed."""


@dataclass
class ToolContext:
    db: Session
    org_id: uuid.UUID
    inst: AgentInstance
    run: Any  # orchestration.models.WorkflowRun
    config: dict
    caller: gateway.Caller
    thresholds: list[Threshold] = field(default_factory=list)


@dataclass
class ToolResult:
    output: dict[str, Any]
    evidence: list[dict[str, Any]] = field(default_factory=list)
    status: str = "succeeded"  # or "unverified" when the effect is handed off without confirmation


def ref(kind: str, id_: Any, label: str) -> dict[str, str]:
    return {"type": kind, "id": str(id_), "label": label[:200]}


# ---- platform ----------------------------------------------------------------------------------------------------

def knowledge_search(ctx: ToolContext, data) -> ToolResult:
    k = ctx.config["knowledge"]
    hits = [h for h in retrieval.search(ctx.db, ctx.caller, data.query, levels=k["access_levels"], top_k=8).hits
            if h.doc_type in k["doc_types"]][:5]
    sources, redacted = [], 0
    for h in hits:
        clean = safety.redact(h.content)
        redacted += clean != h.content
        sources.append({"chunk_id": str(h.chunk_id), "document_id": str(h.document_id),
                        "document_title": h.document_title, "version_no": h.version_no, "section": h.section,
                        "page_number": h.page_number, "excerpt": clean[:800]})
    return ToolResult({"query": data.query, "count": len(sources), "sources": sources, "redactions": redacted},
                      [ref("document_chunk", s["chunk_id"], s["document_title"]) for s in sources])


def escalate(ctx: ToolContext, data) -> ToolResult:
    audit.record(ctx.db, "workflows.escalated", actor_type="agent", org_id=ctx.org_id, target_type="workflow_run",
                 target_id=ctx.run.id, data={"agent": ctx.inst.definition_key, "severity": data.severity,
                                             "reason": data.reason[:300], "subject": data.subject})
    notifications.notify(ctx.db, ctx.org_id, kind="escalation",
                         severity={"normal": "info", "high": "warning"}.get(data.severity, "critical"),
                         title=f"{ctx.inst.name} escalated: {data.reason[:120]}", body=data.reason,
                         link=f"/app/tasks/{ctx.run.id}", subject_type="workflow_run", subject_id=ctx.run.id,
                         dedupe=f"escalation:{ctx.run.id}:{data.subject or data.reason[:80]}")
    return ToolResult({"escalated": True, "severity": data.severity, "reason": data.reason,
                       "subject": data.subject, "delivery": "People who manage tasks were notified"})


# ---- finance -----------------------------------------------------------------------------------------------------

def _last_reminders(db: Session, org_id: uuid.UUID, invoice_ids: list) -> dict[str, datetime]:
    rows = db.execute(select(Draft.related_id, func.max(Draft.sent_at)).where(
        Draft.organization_id == org_id, Draft.kind == "payment_reminder", Draft.status == "sent",
        Draft.related_id.in_(invoice_ids)).group_by(Draft.related_id)).all()
    return {str(i): at for i, at in rows if at}


def invoices_read(ctx: ToolContext, data) -> ToolResult:
    today = business.company_today(ctx.db, ctx.org_id)
    rows = business.query_invoices(ctx.db, ctx.org_id, state=data.state, invoice_id=data.invoice_id,
                                   number=data.number, period=data.period, today=today, limit=data.limit)
    sent = _last_reminders(ctx.db, ctx.org_id, [uuid.UUID(r["id"]) for r in rows])
    for r in rows:
        r["last_reminder_sent_at"] = sent[r["id"]].isoformat() if r["id"] in sent else None
    outstanding = [r for r in rows if r["state"] in ("open", "overdue")]
    out = {"as_of": today.isoformat(), "filter": data.state, "count": len(rows), "found": bool(rows),
           "counts": {k: sum(1 for r in rows if r["state"] == k) for k in ("open", "overdue", "paid", "void")},
           "invoices": [{k: v for k, v in r.items() if k != "payments"} for r in rows],
           "invoiced_by_currency": calc.totals_by_currency([r for r in rows if r["state"] != "void"], "total"),
           "outstanding_by_currency": calc.totals_by_currency(outstanding, "balance"),
           "overdue_by_currency": calc.totals_by_currency([r for r in rows if r["state"] == "overdue"], "balance"),
           "validated_checks": [c for r in rows for c in r["checks"]]}
    return ToolResult(out, [ref("invoice", r["id"], f"Invoice {r['number']}") for r in rows])


def expenses_read(ctx: ToolContext, data) -> ToolResult:
    rows = [business.expense_view(e) for e in business.query_expenses(
        ctx.db, ctx.org_id, expense_id=data.expense_id, status=data.status, period=data.period, limit=data.limit)]
    over = []
    for r in rows:
        limits = [t for t in ctx.thresholds if t.currency == r["currency"]]
        if limits and Decimal(r["amount"]) > (limit := min(limits, key=lambda t: t.amount)).amount:
            over.append({"expense_id": r["id"], "amount": r["amount"], "currency": r["currency"],
                         "limit": str(limit.amount), "rule": limit.statement[:200]})
    return ToolResult({"count": len(rows), "found": bool(rows), "expenses": rows,
                       "totals_by_currency": calc.totals_by_currency(rows, "amount"), "over_limit": over},
                      [ref("expense", r["id"], f"{r['supplier']} {r['amount']} {r['currency']}") for r in rows])


def _reminder_text(inv: dict) -> tuple[str, str]:
    due = (f"was due on {inv['due_date']} ({inv['days_overdue']} days ago)" if inv["days_overdue"]
           else f"is due on {inv['due_date']}")
    body = (f"Dear {inv['customer_name']},\n\n"
            f"Our records show invoice {inv['number']}, issued on {inv['issue_date']}, with an outstanding balance of "
            f"{inv['balance']} {inv['currency']} that {due}.\n\n"
            "If you have already paid, please disregard this message or reply with the payment reference so we can "
            "match it.\n\nThank you.")
    return f"Payment reminder: invoice {inv['number']}", body


def reminder_draft(ctx: ToolContext, data) -> ToolResult:
    rows = business.query_invoices(ctx.db, ctx.org_id, invoice_id=data.invoice_id)
    if not rows:
        raise Refused("Invoice not found")
    inv = rows[0]
    if inv["state"] not in ("open", "overdue"):
        raise Refused(f"Invoice {inv['number']} is {inv['state']}; no reminder is needed")
    if inv["checks"]:
        raise Refused(f"Invoice {inv['number']} has a discrepancy ({inv['checks'][0]}); escalate it instead")
    last = _last_reminders(ctx.db, ctx.org_id, [data.invoice_id]).get(str(data.invoice_id))
    if last and datetime.now(UTC) - last < timedelta(days=REMINDER_GAP_DAYS):
        raise Refused(f"A reminder for invoice {inv['number']} was sent on {last.date().isoformat()}; at most one "
                      f"per {REMINDER_GAP_DAYS} days")
    existing = ctx.db.scalar(select(Draft).where(Draft.organization_id == ctx.org_id, Draft.kind == "payment_reminder",
                                                 Draft.related_id == data.invoice_id, Draft.status == "draft"))
    subject, body = _reminder_text(inv)
    if existing is not None and existing.body == body:
        draft, reused = existing, True
    else:
        draft, reused = business.create_draft(ctx.db, ctx.org_id, kind="payment_reminder", subject=subject,
                                              body=body, recipient=inv["customer_email"], related_type="invoice",
                                              related_id=data.invoice_id, instance_id=ctx.inst.id,
                                              run_id=ctx.run.id), False
    return ToolResult({"draft_id": str(draft.id), "invoice_number": inv["number"], "subject": draft.subject,
                       "recipient": draft.recipient, "balance": inv["balance"], "currency": inv["currency"],
                       "reused_existing": reused, "status": draft.status},
                      [ref("draft", draft.id, draft.subject), ref("invoice", inv["id"], f"Invoice {inv['number']}")])


def _sendable(ctx: ToolContext, draft_id: uuid.UUID) -> tuple[Draft, dict]:
    draft = ctx.db.get(Draft, draft_id)
    if draft is None or draft.organization_id != ctx.org_id or draft.kind != "payment_reminder":
        raise Refused("Payment reminder draft not found")
    if draft.status != "draft":
        raise Refused(f"This reminder is already {draft.status}")
    if not draft.recipient:
        raise Refused("The customer has no email address on the invoice")
    rows = business.query_invoices(ctx.db, ctx.org_id, invoice_id=draft.related_id) if draft.related_id else []
    if not rows or rows[0]["state"] not in ("open", "overdue"):
        raise Refused("The invoice is no longer outstanding; the reminder must not be sent")
    return draft, rows[0]


def reminder_send_parameters(ctx: ToolContext, data) -> dict:
    """The exact action an approver sees and approves (SPEC §6): recipient, subject, full body, invoice balance."""
    draft, inv = _sendable(ctx, data.draft_id)
    return {"draft_id": str(draft.id), "recipient": draft.recipient, "subject": draft.subject, "body": draft.body,
            "invoice_number": inv["number"], "balance": inv["balance"], "currency": inv["currency"]}


def reminder_send(ctx: ToolContext, data) -> ToolResult:
    draft, inv = _sendable(ctx, data.draft_id)
    msg = mailer.send(ctx.db, draft.recipient, draft.subject, draft.body)  # outbox row in this transaction
    draft.status, draft.sent_at = "sent", datetime.now(UTC)
    adapter = get_settings().mailer
    delivery = {"adapter": adapter, "delivered": False, "outbox_id": str(msg.id),
                "label": "Development outbox — stored, not delivered" if adapter == "dev_outbox"
                else "Queued for SMTP delivery; delivery is not confirmed yet"}
    return ToolResult({"sent_to": draft.recipient, "draft_id": str(draft.id), "invoice_number": inv["number"],
                       "delivery": delivery},
                      [ref("draft", draft.id, draft.subject), ref("invoice", inv["id"], f"Invoice {inv['number']}")],
                      status="succeeded" if adapter == "dev_outbox" else "unverified")


# ---- executive ---------------------------------------------------------------------------------------------------

def reports_read(ctx: ToolContext, data) -> ToolResult:
    from abos.orchestration.models import WorkflowRun  # noqa: PLC0415 — orchestration imports this module
    from abos.tools.models import ToolExecution  # noqa: PLC0415

    since = datetime.now(UTC) - timedelta(hours=data.since_hours)
    runs = list(ctx.db.execute(
        select(WorkflowRun, AgentInstance.name).join(AgentInstance, AgentInstance.id == WorkflowRun.instance_id)
        .where(WorkflowRun.organization_id == ctx.org_id, WorkflowRun.created_at >= since,
               WorkflowRun.id != ctx.run.id, WorkflowRun.parent_id.is_(None) | (WorkflowRun.parent_id != ctx.run.id))
        .order_by(WorkflowRun.created_at.desc()).limit(100)).all())
    by_status: dict[str, int] = {}
    for r, _ in runs:
        by_status[r.status] = by_status.get(r.status, 0) + 1
    escalations = ctx.db.scalar(select(func.count()).select_from(ToolExecution).where(
        ToolExecution.organization_id == ctx.org_id, ToolExecution.tool == "escalate",
        ToolExecution.status == "succeeded", ToolExecution.created_at >= since)) or 0
    items = [{"run_id": str(r.id), "agent": name, "task": r.task_title, "status": r.status,
              "finished_at": r.finished_at.isoformat() if r.finished_at else None,
              "summary": (r.output or {}).get("summary", "")[:300]} for r, name in runs]
    return ToolResult({"since": since.isoformat(), "runs": len(runs), "by_status": by_status,
                       "escalations": escalations, "items": items},
                      [ref("workflow_run", i["run_id"], f"{i['agent']}: {i['task']}") for i in items])


def kpi_read(ctx: ToolContext, data) -> ToolResult:
    rows = list(ctx.db.scalars(select(BusinessObjective).where(BusinessObjective.organization_id == ctx.org_id,
                                                               BusinessObjective.status == "active")
                               .order_by(BusinessObjective.title)))
    items = [{"id": str(o.id), "title": o.title, "kpi_name": o.kpi_name,
              "kpi_target": str(o.kpi_target) if o.kpi_target is not None else None, "kpi_unit": o.kpi_unit,
              "target_date": o.target_date.isoformat() if o.target_date else None} for o in rows]
    return ToolResult({"count": len(items), "objectives": items, "measurements": [],
                       "note": "No KPI measurements are recorded yet, so progress against targets can't be computed."},
                      [ref("objective", i["id"], i["title"]) for i in items])


def briefing_draft(ctx: ToolContext, data) -> ToolResult:
    draft = business.create_draft(ctx.db, ctx.org_id, kind="briefing", subject=data.subject, body=data.body,
                                  recipient=None, related_type="workflow_run", related_id=ctx.run.id,
                                  instance_id=ctx.inst.id, run_id=ctx.run.id)
    return ToolResult({"draft_id": str(draft.id), "subject": draft.subject, "status": draft.status,
                       "body_sha256": hashlib.sha256(draft.body.encode()).hexdigest()},
                      [ref("draft", draft.id, draft.subject)])
