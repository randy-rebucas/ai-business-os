"""Mailer boundary.

Every message is first written to `email_outbox` inside the caller's transaction, so mail is only sent for work that
actually committed.

- `dev_outbox` (default outside production): stored, never sent. Dev links are read from the table.
- `smtp`: delivered right after the transaction commits (stdlib smtplib + STARTTLS). Once sent, the body is replaced
  with a placeholder so reset/verification links don't stay readable in the database.

Phase 6 generalises this into the notifications module (email/SMS/in-app adapters, preferences, retries).
"""

import logging
import smtplib
import ssl
import uuid
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from sqlalchemy import event, select
from sqlalchemy.orm import Session

from abos.core.config import Settings, get_settings
from abos.identity.models import EmailOutbox

log = logging.getLogger("abos.mail")

_PENDING = "abos.mail_pending"
SENT_PLACEHOLDER = "[delivered; body not retained]"


def send(db: Session, to_email: str, subject: str, body: str) -> EmailOutbox:
    """Queue a message in the caller's transaction. The returned row's status tells what happened later."""
    s = get_settings()
    if s.mailer == "dev_outbox":
        msg = EmailOutbox(id=uuid.uuid4(), to_email=to_email, subject=subject, body=body, provider="dev_outbox",
                          status="stored")
        db.add(msg)
        return msg
    msg = EmailOutbox(id=uuid.uuid4(), to_email=to_email, subject=subject, body=body, provider="smtp",
                      status="queued")
    db.add(msg)
    db.info.setdefault(_PENDING, []).append(msg.id)
    return msg


@event.listens_for(Session, "after_commit")
def _deliver_after_commit(session: Session) -> None:
    if session.in_nested_transaction():
        return  # SAVEPOINT release, not the real commit (the outbox row isn't committed yet)
    ids = session.info.pop(_PENDING, None)
    if ids:
        deliver(ids)


@event.listens_for(Session, "after_rollback")
def _forget_on_rollback(session: Session) -> None:
    if session.in_nested_transaction():
        return  # a savepoint rollback; deliver() finds no row for a message it removed
    session.info.pop(_PENDING, None)


def _smtp_send(s: Settings, to_email: str, subject: str, body: str) -> None:
    message = EmailMessage()
    message["From"], message["To"], message["Subject"] = s.mail_from, to_email, subject
    message["Date"], message["Message-ID"] = formatdate(localtime=False), make_msgid(domain="abos.local")
    message.set_content(body)
    context = ssl.create_default_context()
    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=s.smtp_timeout_seconds) as smtp:
        if s.smtp_starttls:
            smtp.starttls(context=context)
        if s.smtp_username:
            smtp.login(s.smtp_username, s.smtp_password.get_secret_value() if s.smtp_password else "")
        smtp.send_message(message)


def deliver(ids: list[uuid.UUID] | None = None) -> dict[str, int]:
    """Send queued (or, with ids=None, all queued/failed) smtp messages in a fresh session. Never raises."""
    from abos.core.db import SessionLocal

    s = get_settings()
    result = {"sent": 0, "failed": 0}
    with SessionLocal() as db:
        stmt = select(EmailOutbox).where(EmailOutbox.provider == "smtp")
        stmt = stmt.where(EmailOutbox.id.in_(ids)) if ids else stmt.where(EmailOutbox.status.in_(("queued", "failed")))
        for msg in db.scalars(stmt):
            try:
                if not s.smtp_configured:
                    raise RuntimeError("SMTP is not configured (ABOS_SMTP_HOST)")
                _smtp_send(s, msg.to_email, msg.subject, msg.body)
            except Exception as exc:  # noqa: BLE001 — a mail failure must never break the request that queued it
                msg.status, msg.error = "failed", f"{type(exc).__name__}: {exc}"[:300]
                result["failed"] += 1
                log.warning("mail_failed", extra={"fields": {"outbox_id": str(msg.id), "error": type(exc).__name__}})
            else:
                msg.status, msg.sent_at, msg.error, msg.body = "sent", datetime.now(UTC), None, SENT_PLACEHOLDER
                result["sent"] += 1
        db.commit()
    return result
