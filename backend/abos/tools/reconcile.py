"""Settling unknown outcomes (SPEC step 8: "if the outcome is unknown, mark it as unverified until reconciled").

The ledger row stays exactly as written; a reconciliation row records what was learned later and from where. Today
the one source is the mail outbox: a `reminder.send` handed to SMTP is `unverified` until the outbox reports the
message `sent` (confirmed) or `failed`. Dev-outbox sends are stored, never delivered, and are not reconciled.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from abos.identity.models import EmailOutbox
from abos.tools.models import ExecutionReconciliation, ToolExecution


def reconcile(db: Session) -> dict[str, int]:
    out = {"confirmed": 0, "failed": 0}
    rows = db.scalars(select(ToolExecution).outerjoin(
        ExecutionReconciliation, ExecutionReconciliation.execution_id == ToolExecution.id)
        .where(ToolExecution.status == "unverified", ToolExecution.tool == "reminder.send",
               ExecutionReconciliation.id.is_(None)))
    for x in rows:
        outbox_id = ((x.output or {}).get("delivery") or {}).get("outbox_id")
        msg = db.get(EmailOutbox, uuid.UUID(outbox_id)) if outbox_id else None
        if msg is None or msg.status not in ("sent", "failed"):
            continue
        outcome = "confirmed" if msg.status == "sent" else "failed"
        detail = (f"Mail server accepted the message at {msg.sent_at.isoformat()}" if outcome == "confirmed"
                  else f"Delivery failed: {msg.error or 'unknown error'}")
        try:
            with db.begin_nested():
                db.add(ExecutionReconciliation(organization_id=x.organization_id, execution_id=x.id,
                                               outcome=outcome, source="email_outbox", detail=detail[:500]))
                db.flush()
        except IntegrityError:
            continue
        out[outcome] += 1
    return out


def latest(db: Session, execution_ids: list[uuid.UUID]) -> dict[uuid.UUID, ExecutionReconciliation]:
    if not execution_ids:
        return {}
    return {r.execution_id: r for r in db.scalars(select(ExecutionReconciliation).where(
        ExecutionReconciliation.execution_id.in_(execution_ids)))}
