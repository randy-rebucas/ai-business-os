"""Notifications (SPEC §3 step 8): in-app records, per-user preferences, and one delivery row per channel attempt.

A notification is always stored in-app for each recipient (recipients are chosen by permission, never by role).
Email and SMS are deliveries: immediate for alerts at or above the user's chosen severity, otherwise collected in the
daily digest at the user's local digest time. Every delivery records its provider, status, attempts and error, and is
retried with backoff a bounded number of times. Dev providers store instead of sending and say so.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from abos.core.db import Base, IdMixin, TenantMixin, TimestampMixin

KINDS = ("action_required", "escalation", "run_failed", "run_unverified", "budget", "report_ready")
SEVERITIES = ("info", "warning", "critical")


class Notification(IdMixin, TenantMixin, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_user_unread", "organization_id", "user_id", "read_at"),
        Index("ix_notifications_org_created", "organization_id", "created_at"),  # retention purge
        # The same event never notifies the same person twice (re-delivered triggers, retried jobs).
        Index("uq_notification_dedupe", "organization_id", "user_id", "dedupe_key", unique=True,
              postgresql_where=text("dedupe_key IS NOT NULL")),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(30))
    severity: Mapped[str] = mapped_column(String(10))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(300))  # an app path, e.g. /app/tasks/{id}
    subject_type: Mapped[str | None] = mapped_column(String(30))
    subject_id: Mapped[uuid.UUID | None] = mapped_column()
    dedupe_key: Mapped[str | None] = mapped_column(String(200))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    digested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # included in an email digest
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class NotificationPreference(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "notification_preferences"
    __table_args__ = (UniqueConstraint("organization_id", "user_id", name="uq_notification_pref_user"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    email_immediate: Mapped[str] = mapped_column(String(10), default="critical")  # off | warning | critical
    email_digest: Mapped[bool] = mapped_column(Boolean, default=True)
    digest_time: Mapped[str] = mapped_column(String(5), default="08:00")  # HH:MM in the company time zone
    sms_critical: Mapped[bool] = mapped_column(Boolean, default=False)
    sms_number: Mapped[str | None] = mapped_column(String(20))  # E.164


class NotificationDelivery(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "notification_deliveries"
    __table_args__ = (
        Index("ix_notification_deliveries_due", "status", "next_attempt_at"),
        Index("uq_notification_delivery_dedupe", "organization_id", "dedupe_key", unique=True,
              postgresql_where=text("dedupe_key IS NOT NULL")),
    )

    notification_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("notifications.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    channel: Mapped[str] = mapped_column(String(10))  # email | sms
    kind: Mapped[str] = mapped_column(String(10))  # alert | digest
    provider: Mapped[str] = mapped_column(String(20))  # dev_outbox | smtp | dev_sms | …
    to_address: Mapped[str] = mapped_column(String(320))
    subject: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    # queued → handed_off (to the mail queue) → sent | failed (retried) · stored (dev: kept, never sent) ·
    # suppressed (delivery limit / missing address) · abandoned (retries exhausted)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(300))
    external_id: Mapped[str | None] = mapped_column(String(100))  # outbox id / provider message id
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dedupe_key: Mapped[str | None] = mapped_column(String(200))  # digest:{user}:{date}
