import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator
from sqlalchemy.orm import Session

from abos.core.db import get_db
from abos.core.errors import AppError
from abos.identity.deps import OrgContext, require_org_permission
from abos.notifications import service
from abos.reporting.service import zone_of
from abos.usage import service as usage

notifications_router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])
usage_router = APIRouter(prefix="/api/v1/usage", tags=["usage"])

READ = require_org_permission("notification.read")
USAGE = require_org_permission("usage.read")


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    severity: str
    title: str
    body: str
    link: str | None
    subject_type: str | None
    subject_id: uuid.UUID | None
    read_at: datetime | None
    digested_at: datetime | None
    created_at: datetime


class PreferenceIn(BaseModel):
    email_immediate: Literal["off", "warning", "critical"] = "critical"
    email_digest: bool = True
    digest_time: Annotated[str, StringConstraints(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")] = "08:00"
    sms_critical: bool = False
    sms_number: Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^\+[1-9]\d{6,14}$")] | None = None

    @model_validator(mode="after")
    def _number(self) -> "PreferenceIn":
        if self.sms_critical and not self.sms_number:
            raise ValueError("Add a phone number in international format (+63…) to receive SMS alerts")
        return self


class PreferenceOut(PreferenceIn):
    model_config = ConfigDict(from_attributes=True)

    sms_number: str | None = None
    sms_provider: str = "none"


class DeliveryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    notification_id: uuid.UUID | None
    channel: str
    kind: str
    provider: str
    to_address: str
    subject: str
    status: str
    attempts: int
    next_attempt_at: datetime | None
    last_error: str | None
    sent_at: datetime | None
    created_at: datetime


@notifications_router.get("", response_model=list[NotificationOut])
def notifications(unread: bool = False, limit: int = Query(100, ge=1, le=200), ctx: OrgContext = Depends(READ),
                  db: Session = Depends(get_db)):
    return service.for_user(db, ctx, unread=unread, limit=limit)


@notifications_router.get("/unread-count")
def unread_count(ctx: OrgContext = Depends(READ), db: Session = Depends(get_db)):
    return {"unread": service.unread_count(db, ctx)}


@notifications_router.post("/{notification_id}/read")
def mark_read(notification_id: uuid.UUID, ctx: OrgContext = Depends(READ), db: Session = Depends(get_db)):
    return {"marked": service.mark_read(db, ctx, notification_id)}


@notifications_router.post("/read-all")
def mark_all_read(ctx: OrgContext = Depends(READ), db: Session = Depends(get_db)):
    return {"marked": service.mark_read(db, ctx, None)}


@notifications_router.get("/preferences", response_model=PreferenceOut)
def get_preferences(ctx: OrgContext = Depends(READ), db: Session = Depends(get_db)):
    from abos.core.config import get_settings  # noqa: PLC0415

    pref = service.preference(db, ctx.org_id, ctx.user.id)
    return PreferenceOut.model_validate(pref).model_copy(update={"sms_provider": get_settings().sms_provider})


@notifications_router.put("/preferences", response_model=PreferenceOut)
def put_preferences(data: PreferenceIn, ctx: OrgContext = Depends(READ), db: Session = Depends(get_db)):
    from abos.core.config import get_settings  # noqa: PLC0415

    pref = service.save_preference(db, ctx, data)
    return PreferenceOut.model_validate(pref).model_copy(update={"sms_provider": get_settings().sms_provider})


@notifications_router.get("/deliveries", response_model=list[DeliveryOut])
def deliveries(ctx: OrgContext = Depends(READ), db: Session = Depends(get_db)):
    return service.deliveries(db, ctx)


@usage_router.get("")
def usage_summary(date_from: date | None = None, date_to: date | None = None, ctx: OrgContext = Depends(USAGE),
                  db: Session = Depends(get_db)):
    date_to = date_to or datetime.now(UTC).astimezone(zone_of(db, ctx.org_id)).date()
    date_from = date_from or date_to.replace(day=1)
    if date_from > date_to or (date_to - date_from) > timedelta(days=366):
        raise AppError(422, "validation_error", "Choose a range of at most one year, oldest date first")
    return usage.summary(db, ctx.org_id, date_from=date_from, date_to=date_to)

