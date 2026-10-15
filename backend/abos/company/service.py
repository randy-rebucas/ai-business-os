import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from abos.audit import service as audit
from abos.company import schemas as s
from abos.company.models import (
    BusinessObjective,
    BusinessProcess,
    CompanyLocation,
    CompanyProfile,
    Department,
    JobRole,
    Offering,
    OperationalChallenge,
    SoftwareSystem,
)
from abos.core.db import Base
from abos.core.errors import AppError, conflict, not_found
from abos.identity.deps import OrgContext


def _validation_error(exc: ValidationError) -> AppError:
    details = [{"loc": ["body", *[str(p) for p in e["loc"]]], "msg": e["msg"], "type": e["type"]}
               for e in exc.errors()]
    return AppError(422, "validation_error", "Invalid request", details)


# ---- profile -----------------------------------------------------------------------------------

def create_profile(db: Session, org_id: uuid.UUID, company_name: str) -> CompanyProfile:
    profile = CompanyProfile(organization_id=org_id, company_name=company_name, holidays=[],
                             notification_channels=s.NotificationChannels().model_dump(), skipped_sections=[])
    db.add(profile)
    return profile


def get_profile(db: Session, org_id: uuid.UUID) -> CompanyProfile:
    profile = db.scalar(select(CompanyProfile).where(CompanyProfile.organization_id == org_id))
    if profile is None:  # every org gets one at creation; this only guards against manual DB edits
        raise not_found("Company profile")
    return profile


def update_profile(db: Session, ctx: OrgContext, data: s.ProfileUpdateIn) -> CompanyProfile:
    profile = get_profile(db, ctx.org_id)
    changes = data.model_dump(mode="json", exclude_unset=True)
    if "monthly_ai_budget" in changes:  # keep the Decimal, not its JSON string
        changes["monthly_ai_budget"] = data.monthly_ai_budget
    changed = [k for k, v in changes.items() if getattr(profile, k) != v]
    for key in changed:
        setattr(profile, key, changes[key])
    if changed:
        audit.record(db, "company.profile_updated", actor_id=ctx.user.id, org_id=ctx.org_id,
                     target_type="company_profile", target_id=profile.id, data={"fields": sorted(changed)},
                     ip=ctx.meta.ip)
    db.commit()
    db.refresh(profile)
    return profile


def complete_onboarding(db: Session, ctx: OrgContext) -> CompanyProfile:
    profile = get_profile(db, ctx.org_id)
    if profile.onboarding_completed_at is None:
        profile.onboarding_completed_at = datetime.now(UTC)
        audit.record(db, "company.onboarding_completed", actor_id=ctx.user.id, org_id=ctx.org_id,
                     target_type="company_profile", target_id=profile.id,
                     data={"completeness": completeness(db, ctx.org_id).percent}, ip=ctx.meta.ip)
        db.commit()
        db.refresh(profile)
    return profile


# ---- collections -------------------------------------------------------------------------------

@dataclass(frozen=True)
class Collection:
    key: str  # URL segment
    label: str
    model: type[Base]
    create: type[BaseModel]
    patch: type[BaseModel]
    out: type[BaseModel]
    order_by: str


COLLECTIONS: dict[str, Collection] = {c.key: c for c in (
    Collection("locations", "location", CompanyLocation, s.LocationIn, s.LocationPatch, s.LocationOut, "name"),
    Collection("departments", "department", Department, s.DepartmentIn, s.DepartmentPatch, s.DepartmentOut, "name"),
    Collection("job-roles", "job role", JobRole, s.JobRoleIn, s.JobRolePatch, s.JobRoleOut, "title"),
    Collection("offerings", "offering", Offering, s.OfferingIn, s.OfferingPatch, s.OfferingOut, "name"),
    Collection("objectives", "objective", BusinessObjective, s.ObjectiveIn, s.ObjectivePatch, s.ObjectiveOut,
               "created_at"),
    Collection("processes", "process", BusinessProcess, s.ProcessIn, s.ProcessPatch, s.ProcessOut, "name"),
    Collection("software", "software system", SoftwareSystem, s.SoftwareIn, s.SoftwarePatch, s.SoftwareOut, "name"),
    Collection("challenges", "challenge", OperationalChallenge, s.ChallengeIn, s.ChallengePatch, s.ChallengeOut,
               "created_at"),
)}

MAX_ITEMS_PER_COLLECTION = 500


def list_items(db: Session, org_id: uuid.UUID, c: Collection) -> list[Any]:
    model = c.model
    return list(db.scalars(select(model).where(model.organization_id == org_id)
                           .order_by(getattr(model, c.order_by))))


def _get_item(db: Session, org_id: uuid.UUID, c: Collection, item_id: uuid.UUID) -> Any:
    item = db.get(c.model, item_id)
    if item is None or item.organization_id != org_id:
        raise not_found(c.label.capitalize())
    return item


def _check_refs(db: Session, org_id: uuid.UUID, values: dict[str, Any]) -> None:
    """A department reference must point at this organization's department (ids from the body are untrusted)."""
    dept_id = values.get("department_id")
    if dept_id is not None:
        dept = db.get(Department, dept_id)
        if dept is None or dept.organization_id != org_id:
            raise AppError(422, "validation_error", "Invalid request",
                           [{"loc": ["body", "department_id"], "msg": "Unknown department", "type": "value_error"}])


def _unset_other_primaries(db: Session, org_id: uuid.UUID, keep: uuid.UUID) -> None:
    for loc in db.scalars(select(CompanyLocation).where(CompanyLocation.organization_id == org_id,
                                                        CompanyLocation.is_primary.is_(True),
                                                        CompanyLocation.id != keep)):
        loc.is_primary = False


@contextmanager
def _unique_guard(db: Session, c: Collection) -> Iterator[None]:
    """Turn a unique-constraint violation (at flush or commit) into a 409."""
    try:
        yield
    except IntegrityError as exc:
        db.rollback()
        raise conflict(f"A {c.label} with this name already exists") from exc


def create_item(db: Session, ctx: OrgContext, c: Collection, data: BaseModel) -> Any:
    count = db.scalar(select(func.count()).select_from(c.model).where(c.model.organization_id == ctx.org_id)) or 0
    if count >= MAX_ITEMS_PER_COLLECTION:
        raise conflict(f"Limit of {MAX_ITEMS_PER_COLLECTION} {c.label} records reached")
    values = data.model_dump()
    _check_refs(db, ctx.org_id, values)
    item = c.model(organization_id=ctx.org_id, **values)
    with _unique_guard(db, c):
        db.add(item)
        db.flush()
        if getattr(item, "is_primary", False):
            _unset_other_primaries(db, ctx.org_id, item.id)
        audit.record(db, f"company.{c.key}.created", actor_id=ctx.user.id, org_id=ctx.org_id, target_type=c.key,
                     target_id=item.id, ip=ctx.meta.ip)
        db.commit()
    db.refresh(item)
    return item


def update_item(db: Session, ctx: OrgContext, c: Collection, item_id: uuid.UUID, patch: BaseModel) -> Any:
    item = _get_item(db, ctx.org_id, c, item_id)
    current = {k: getattr(item, k) for k in c.create.model_fields}
    try:  # merge then validate as a full record, so required fields and validators still apply
        merged = c.create.model_validate({**current, **patch.model_dump(exclude_unset=True)})
    except ValidationError as exc:
        raise _validation_error(exc) from exc
    values = merged.model_dump()
    _check_refs(db, ctx.org_id, values)
    changed = [k for k, v in values.items() if getattr(item, k) != v]
    with _unique_guard(db, c):
        for k in changed:
            setattr(item, k, values[k])
        if getattr(item, "is_primary", False):
            _unset_other_primaries(db, ctx.org_id, item.id)
        if changed:
            audit.record(db, f"company.{c.key}.updated", actor_id=ctx.user.id, org_id=ctx.org_id,
                         target_type=c.key, target_id=item.id, data={"fields": sorted(changed)}, ip=ctx.meta.ip)
        db.commit()
    db.refresh(item)
    return item


def delete_item(db: Session, ctx: OrgContext, c: Collection, item_id: uuid.UUID) -> None:
    item = _get_item(db, ctx.org_id, c, item_id)
    db.delete(item)
    audit.record(db, f"company.{c.key}.deleted", actor_id=ctx.user.id, org_id=ctx.org_id, target_type=c.key,
                 target_id=item_id, ip=ctx.meta.ip)
    db.commit()


# ---- completeness (ADR-006) --------------------------------------------------------------------

SECTION_LABELS = {
    "basics": "Company basics", "offerings": "Products & services", "customers": "Target customers",
    "locations": "Locations & branches", "structure": "Size & structure", "roles": "Job roles",
    "objectives": "Objectives & KPIs", "operations": "Operating hours & time zone", "processes": "Business processes",
    "software": "Current software", "challenges": "Operational challenges", "reporting": "Reporting & notifications",
    "budget": "AI workforce budget",
}


def _counts(db: Session, org_id: uuid.UUID) -> dict[str, int]:
    out = {}
    for c in COLLECTIONS.values():
        out[c.key] = db.scalar(select(func.count()).select_from(c.model)
                               .where(c.model.organization_id == org_id)) or 0
    return out


def completeness(db: Session, org_id: uuid.UUID) -> s.CompletenessOut:
    p = get_profile(db, org_id)
    n = _counts(db, org_id)
    needs: dict[str, list[str]] = {
        "basics": [m for m, ok in (("Industry", p.industry), ("Company description", p.description),
                                   ("Legal or trading name", p.legal_name or p.trading_name)) if not ok],
        "offerings": [] if n["offerings"] else ["At least one product or service"],
        "customers": [] if p.target_customers else ["Who your customers are"],
        "locations": [] if n["locations"] else ["At least one location or branch"],
        "structure": [m for m, ok in (("Company size", p.company_size), ("Departments", n["departments"])) if not ok],
        "roles": [] if n["job-roles"] else ["Existing job roles"],
        "objectives": [] if n["objectives"] else ["At least one business objective or KPI"],
        "operations": [m for m, ok in (("Time zone", p.timezone), ("Operating days and hours", p.operating_schedule))
                       if not ok],
        "processes": [] if n["processes"] else ["Key business processes and approval procedures"],
        "software": [] if n["software"] else ["Software you use today"],
        "challenges": [] if n["challenges"] else ["Current operational challenges"],
        "reporting": [] if p.reporting_cadence else ["Preferred reporting cadence"],
        "budget": [] if p.monthly_ai_budget is not None else ["Monthly AI workforce budget"],
    }
    # Multi-item sections are "partial" when some but not all items are present.
    totals = {"basics": 3, "structure": 2, "operations": 2}
    sections, complete = [], 0
    for key in s.SECTIONS:
        missing = needs[key]
        if not missing:
            status = "complete"
            complete += 1
        elif key in p.skipped_sections:
            status = "skipped"
        elif key in totals and len(missing) < totals[key]:
            status = "partial"
        else:
            status = "missing"
        sections.append(s.SectionStatus(key=key, label=SECTION_LABELS[key], status=status, missing=missing))
    return s.CompletenessOut(percent=round(100 * complete / len(s.SECTIONS)), sections=sections,
                             missing_count=sum(len(x.missing) for x in sections))
