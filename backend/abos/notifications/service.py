"""Notifications service (SPEC §3 step 8 'Notifications', ADR-030).

`notify` runs inside the transaction that caused the event, so a notification exists iff the event committed:
- recipients are the workspace members whose role grants the permission tied to the kind (never a role name);
- every recipient gets an in-app notification (deduplicated per event);
- an email goes out immediately when the severity reaches the user's `email_immediate` setting, an SMS when it is
  critical and the user enabled SMS — each as a `notification_deliveries` row sent by a background job;
- everything else waits for the user's daily digest at their digest time in the company time zone.
Deliveries respect per-user limits (over the limit → suppressed, still in the digest), record provider / status /
attempts / error, and are retried with exponential backoff until `notify_max_attempts`.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from abos.company import service as company
from abos.core.config import get_settings
from abos.core.errors import not_found
from abos.identity.deps import OrgContext
from abos.identity.models import EmailOutbox, OrganizationMembership, User
from abos.identity.permissions import org_role_has
from abos.jobs import service as jobs
from abos.knowledge.models import JobRun
from abos.notifications import channels
from abos.notifications.models import Notification, NotificationDelivery, NotificationPreference

log = logging.getLogger("abos.notifications")
JOB_KIND = "notification_delivery"
RANK = {"info": 0, "warning": 1, "critical": 2, "off": 99}
# Who hears about what: the permission that makes the event actionable for a member.
RECIPIENT_PERMISSION = {
    "action_required": "approval.decide",
    "escalation": "task.manage",
    "run_failed": "task.manage",
    "run_unverified": "task.manage",
    "budget": "usage.read",
    "report_ready": "report.read",
}


def _now() -> datetime:
    return datetime.now(UTC)


def preference(db: Session, org_id: uuid.UUID, user_id: uuid.UUID) -> NotificationPreference:
    """The stored preference, or the defaults (critical alerts by email, daily digest at 08:00, no SMS)."""
    pref = db.scalar(select(NotificationPreference).where(NotificationPreference.organization_id == org_id,
                                                          NotificationPreference.user_id == user_id))
    return pref or NotificationPreference(organization_id=org_id, user_id=user_id, email_immediate="critical",
                                          email_digest=True, digest_time="08:00", sms_critical=False)


def recipients(db: Session, org_id: uuid.UUID, kind: str) -> list[User]:
    perm = RECIPIENT_PERMISSION[kind]
    rows = db.execute(select(OrganizationMembership, User).join(User, User.id == OrganizationMembership.user_id)
                      .where(OrganizationMembership.organization_id == org_id)).all()
    return [u for m, u in rows if org_role_has(m.role, perm)]


def notify(db: Session, org_id: uuid.UUID, *, kind: str, severity: str, title: str, body: str,
           link: str | None = None, subject_type: str | None = None, subject_id: uuid.UUID | None = None,
           dedupe: str | None = None) -> list[Notification]:
    created = []
    for user in recipients(db, org_id, kind):
        if dedupe and db.scalar(select(Notification.id).where(Notification.organization_id == org_id,
                                                              Notification.user_id == user.id,
                                                              Notification.dedupe_key == dedupe)):
            continue
        n = Notification(organization_id=org_id, user_id=user.id, kind=kind, severity=severity, title=title[:200],
                         body=body, link=link, subject_type=subject_type, subject_id=subject_id, dedupe_key=dedupe)
        try:
            with db.begin_nested():
                db.add(n)
                db.flush()
        except IntegrityError:
            continue  # notified concurrently
        created.append(n)
        pref = preference(db, org_id, user.id)
        if RANK[severity] >= RANK[pref.email_immediate]:
            _queue(db, n, user, "email", user.email)
        if severity == "critical" and pref.sms_critical:
            _queue(db, n, user, "sms", pref.sms_number or "")
    return created


def _queue(db: Session, n: Notification, user: User, channel: str, to: str) -> NotificationDelivery:
    prefix = {"critical": "[Critical] ", "warning": "[Action needed] "}.get(n.severity, "")
    link = f"\n\n{get_settings().app_base_url}{n.link}" if n.link else ""
    d = NotificationDelivery(organization_id=n.organization_id, notification_id=n.id, user_id=user.id,
                             channel=channel, kind="alert", provider="pending", to_address=to,
                             subject=f"{prefix}{n.title}"[:300], body=f"{n.body}{link}", status="queued")
    db.add(d)
    db.flush()
    jobs.enqueue(db, n.organization_id, JOB_KIND, d.id)
    return d


# ---- delivery ----------------------------------------------------------------------------------------------------

def _within_limit(db: Session, d: NotificationDelivery) -> bool:
    s = get_settings()
    limit, window = (s.notify_email_per_hour, timedelta(hours=1)) if d.channel == "email" \
        else (s.notify_sms_per_day, timedelta(days=1))
    used = db.scalar(select(func.count()).select_from(NotificationDelivery).where(
        NotificationDelivery.user_id == d.user_id, NotificationDelivery.channel == d.channel,
        NotificationDelivery.kind == "alert", NotificationDelivery.id != d.id,
        NotificationDelivery.status.in_(("handed_off", "sent", "stored")),
        NotificationDelivery.sent_at >= _now() - window)) or 0
    return used < limit


def deliver(db: Session, d: NotificationDelivery) -> None:
    """Send one queued (or due-for-retry) delivery. Never raises: failures are recorded and retried later."""
    if d.status not in ("queued", "failed"):
        return
    if not d.to_address:
        d.status, d.last_error = "suppressed", "No address for this channel"
        return
    if d.kind == "alert" and not _within_limit(db, d):
        d.status, d.last_error = "suppressed", "Delivery limit reached; included in the next digest"
        if d.notification_id and (n := db.get(Notification, d.notification_id)):
            n.digested_at = None
        return
    d.attempts += 1
    try:
        with db.begin_nested():
            sent = channels.send(db, d.channel, d.to_address, d.subject, d.body, d.id)
    except channels.NotConfigured as exc:
        d.status, d.last_error, d.provider = "suppressed", str(exc)[:300], "none"
        return
    except Exception as exc:  # noqa: BLE001 — a provider fault is a failed attempt, not a crash
        _failed(d, f"{type(exc).__name__}: {exc}")
        return
    d.status, d.provider, d.external_id, d.last_error = sent.status, sent.provider, sent.external_id, sent.label
    d.sent_at, d.next_attempt_at = _now(), None


def _failed(d: NotificationDelivery, error: str) -> None:
    d.last_error = error[:300]
    if d.attempts >= get_settings().notify_max_attempts:
        d.status, d.next_attempt_at = "abandoned", None
    else:
        d.status, d.next_attempt_at = "failed", _now() + timedelta(minutes=2 ** d.attempts)


@jobs.handler(JOB_KIND)
def run_delivery(db: Session, job: JobRun) -> None:
    d = db.get(NotificationDelivery, job.target_id)
    if d is None:
        raise jobs.JobFailed("Delivery not found")
    deliver(db, d)
    db.commit()


def reconcile_email(db: Session) -> dict[str, int]:
    """Handed-off emails take their final status from the mail outbox (SMTP outcome); failures are retried."""
    out = {"sent": 0, "failed": 0}
    for d in db.scalars(select(NotificationDelivery).where(NotificationDelivery.status == "handed_off",
                                                           NotificationDelivery.channel == "email")):
        msg = db.get(EmailOutbox, uuid.UUID(d.external_id)) if d.external_id else None
        if msg is None:
            continue
        if msg.status == "sent":
            d.status, d.sent_at = "sent", msg.sent_at or _now()
            out["sent"] += 1
        elif msg.status == "failed":
            _failed(d, msg.error or "SMTP delivery failed")
            out["failed"] += 1
    return out


def retry_due(db: Session, now: datetime) -> int:
    due = list(db.scalars(select(NotificationDelivery).where(NotificationDelivery.status == "failed",
                                                             NotificationDelivery.next_attempt_at <= now)))
    for d in due:
        jobs.enqueue(db, d.organization_id, JOB_KIND, d.id)
    return len(due)


# ---- digests -----------------------------------------------------------------------------------------------------

def digests(db: Session, now: datetime) -> int:
    """Daily digest per member at their digest time (company time zone): every notification not yet digested."""
    sent = 0
    pending = db.execute(select(Notification.organization_id, Notification.user_id)
                         .where(Notification.digested_at.is_(None)).distinct()).all()
    for org_id, user_id in pending:
        pref = preference(db, org_id, user_id)
        if not pref.email_digest:
            continue
        tz = company.get_profile(db, org_id).timezone or "UTC"
        local = now.astimezone(ZoneInfo(tz))
        if local.strftime("%H:%M") < pref.digest_time:
            continue
        key = f"digest:{user_id}:{local.date().isoformat()}"
        if db.scalar(select(NotificationDelivery.id).where(NotificationDelivery.organization_id == org_id,
                                                           NotificationDelivery.dedupe_key == key)):
            continue
        items = list(db.scalars(select(Notification).where(Notification.organization_id == org_id,
                                                           Notification.user_id == user_id,
                                                           Notification.digested_at.is_(None))
                                .order_by(Notification.created_at)))
        user = db.get(User, user_id)
        base = get_settings().app_base_url
        lines = [f"- [{n.severity}] {n.title}" + (f" — {base}{n.link}" if n.link else "") for n in items[:50]]
        if len(items) > 50:
            lines.append(f"…and {len(items) - 50} more in the notification center: {base}/app/notifications")
        d = NotificationDelivery(organization_id=org_id, user_id=user_id, channel="email", kind="digest",
                                 provider="pending", to_address=user.email,
                                 subject=f"Your AI workforce digest — {local.date().isoformat()}",
                                 body=f"{len(items)} update(s) since your last digest:\n\n" + "\n".join(lines),
                                 status="queued", dedupe_key=key)
        try:
            with db.begin_nested():
                db.add(d)
                db.flush()
        except IntegrityError:
            continue
        for n in items:
            n.digested_at = now
        jobs.enqueue(db, org_id, JOB_KIND, d.id)
        sent += 1
    return sent


# ---- people ------------------------------------------------------------------------------------------------------

def for_user(db: Session, ctx: OrgContext, *, unread: bool = False, limit: int = 100) -> list[Notification]:
    stmt = select(Notification).where(Notification.organization_id == ctx.org_id, Notification.user_id == ctx.user.id)
    if unread:
        stmt = stmt.where(Notification.read_at.is_(None))
    return list(db.scalars(stmt.order_by(Notification.created_at.desc()).limit(limit)))


def unread_count(db: Session, ctx: OrgContext) -> int:
    return db.scalar(select(func.count()).select_from(Notification).where(
        Notification.organization_id == ctx.org_id, Notification.user_id == ctx.user.id,
        Notification.read_at.is_(None))) or 0


def mark_read(db: Session, ctx: OrgContext, notification_id: uuid.UUID | None) -> int:
    stmt = select(Notification).where(Notification.organization_id == ctx.org_id, Notification.user_id == ctx.user.id,
                                      Notification.read_at.is_(None))
    if notification_id:
        stmt = stmt.where(Notification.id == notification_id)
    rows = list(db.scalars(stmt))
    if notification_id and not rows and not db.scalar(select(Notification.id).where(
            Notification.id == notification_id, Notification.user_id == ctx.user.id,
            Notification.organization_id == ctx.org_id)):
        raise not_found("Notification")
    for n in rows:
        n.read_at = _now()
    db.commit()
    return len(rows)


def save_preference(db: Session, ctx: OrgContext, data) -> NotificationPreference:
    pref = db.scalar(select(NotificationPreference).where(NotificationPreference.organization_id == ctx.org_id,
                                                          NotificationPreference.user_id == ctx.user.id))
    if pref is None:
        pref = NotificationPreference(organization_id=ctx.org_id, user_id=ctx.user.id)
        db.add(pref)
    for k, v in data.model_dump().items():
        setattr(pref, k, v)
    db.commit()
    db.refresh(pref)
    return pref


def deliveries(db: Session, ctx: OrgContext, limit: int = 50) -> list[NotificationDelivery]:
    return list(db.scalars(select(NotificationDelivery).where(NotificationDelivery.organization_id == ctx.org_id,
                                                              NotificationDelivery.user_id == ctx.user.id)
                           .order_by(NotificationDelivery.created_at.desc()).limit(limit)))
