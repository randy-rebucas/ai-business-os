"""Delivery channels behind one interface, so no messaging provider is hard-coded (SPEC step 8).

- email → `identity.mailer` (dev outbox stores, SMTP delivers after commit; the outbox row's status is reconciled
  into the delivery later).
- sms → an `SmsProvider`. `dev` stores the message and says so; `none` means SMS is not configured. A real provider
  (Twilio, Vonage, …) is one more class implementing `send`, using the delivery id as its idempotency key.
"""

import uuid
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.orm import Session

from abos.core.config import get_settings
from abos.identity import mailer

DEV_LABEL = "Development adapter — stored, not delivered"


class NotConfigured(Exception):
    """The channel can't deliver at all (no provider); the delivery is suppressed, not retried."""


@dataclass
class Sent:
    status: str            # handed_off (delivery confirmed later) | stored (dev: kept, never delivered)
    provider: str
    external_id: str | None
    label: str | None = None


class SmsProvider(Protocol):
    name: str

    def send(self, to: str, text: str, idempotency_key: str) -> Sent: ...


class DevSms:
    name = "dev_sms"

    def send(self, to: str, text: str, idempotency_key: str) -> Sent:
        return Sent("stored", self.name, f"dev-{idempotency_key}", DEV_LABEL)


class NoSms:
    name = "none"

    def send(self, to: str, text: str, idempotency_key: str) -> Sent:
        raise NotConfigured("No SMS provider is configured")


def sms_provider() -> SmsProvider:
    return DevSms() if get_settings().sms_provider == "dev" else NoSms()


def send_email(db: Session, to: str, subject: str, body: str) -> Sent:
    msg = mailer.send(db, to, subject, body)
    if msg.provider == "dev_outbox":
        return Sent("stored", "dev_outbox", str(msg.id), DEV_LABEL)
    return Sent("handed_off", "smtp", str(msg.id))


def send(db: Session, channel: str, to: str, subject: str, body: str, delivery_id: uuid.UUID) -> Sent:
    if channel == "email":
        return send_email(db, to, subject, body)
    return sms_provider().send(to, f"{subject}: {body}"[:480], str(delivery_id))
