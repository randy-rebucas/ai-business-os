import re
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

Short = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Text = Annotated[str, StringConstraints(strip_whitespace=True, max_length=5000)]

CompanySize = Literal["1", "2-10", "11-50", "51-200", "201-1000", "1000+"]
Cadence = Literal["daily", "weekly", "monthly"]
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
SECTIONS = ("basics", "offerings", "customers", "locations", "structure", "roles", "objectives", "operations",
            "processes", "software", "challenges", "reporting", "budget")
Section = Literal["basics", "offerings", "customers", "locations", "structure", "roles", "objectives", "operations",
                  "processes", "software", "challenges", "reporting", "budget"]
_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def validate_timezone(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("Unknown time zone; use an IANA name such as Asia/Manila") from exc
    return value


def timezone_names() -> list[str]:
    return sorted(available_timezones())


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class DayHours(BaseModel):
    open: str
    close: str

    @model_validator(mode="after")
    def _check(self) -> "DayHours":
        if not (_HHMM.match(self.open) and _HHMM.match(self.close)):
            raise ValueError("Times must be HH:MM (24-hour)")
        if self.open >= self.close:
            raise ValueError("Closing time must be after opening time")
        return self


class Holiday(BaseModel):
    date: date
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class NotificationChannels(BaseModel):
    in_app: bool = True
    email: bool = False
    sms: bool = False


# ---- profile -----------------------------------------------------------------------------------

class ProfileUpdateIn(BaseModel):
    """Partial update: only fields present in the request body change. Send null to clear a field."""

    company_name: Short | None = None
    legal_name: Short | None = None
    trading_name: Short | None = None
    industry: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] | None = None
    business_category: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] | None = None
    description: Text | None = None
    target_customers: Text | None = None
    company_size: CompanySize | None = None
    employee_count: Annotated[int, Field(ge=0, le=10_000_000)] | None = None
    organization_structure: Text | None = None
    timezone: str | None = None
    operating_schedule: dict[Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"], DayHours | None] | None = None
    holidays: Annotated[list[Holiday], Field(max_length=100)] | None = None
    reporting_cadence: Cadence | None = None
    notification_channels: NotificationChannels | None = None
    monthly_ai_budget: Annotated[Decimal, Field(ge=0, le=10_000_000, decimal_places=2)] | None = None
    budget_currency: Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")] | None = None
    skipped_sections: Annotated[list[Section], Field(max_length=len(SECTIONS))] | None = None

    _tz = field_validator("timezone")(validate_timezone)

    @model_validator(mode="after")
    def _name_not_cleared(self) -> "ProfileUpdateIn":
        if "company_name" in self.model_fields_set and self.company_name is None:
            raise ValueError("company_name cannot be cleared")
        return self


class ProfileOut(ORM):
    id: uuid.UUID
    company_name: str
    legal_name: str | None
    trading_name: str | None
    industry: str | None
    business_category: str | None
    description: str | None
    target_customers: str | None
    company_size: str | None
    employee_count: int | None
    organization_structure: str | None
    timezone: str | None
    operating_schedule: dict | None
    holidays: list[dict]
    reporting_cadence: str | None
    notification_channels: dict
    monthly_ai_budget: Decimal | None
    budget_currency: str
    skipped_sections: list[str]
    onboarding_completed_at: datetime | None
    updated_at: datetime


class SectionStatus(BaseModel):
    key: str
    label: str
    status: Literal["complete", "partial", "missing", "skipped"]
    missing: list[str]  # human-readable items still needed


class CompletenessOut(BaseModel):
    percent: int
    sections: list[SectionStatus]
    missing_count: int


# ---- collections -------------------------------------------------------------------------------
# Each collection has In (create; also the full-replace shape), Patch (all optional) and Out.

def _partial(model: type[BaseModel], name: str) -> type[BaseModel]:
    """All-optional copy of a create schema for PATCH."""
    from pydantic import create_model

    fields = {k: (f.annotation | None, None) for k, f in model.model_fields.items()}
    return create_model(name, __base__=BaseModel, **fields)  # type: ignore[call-overload]


class LocationIn(BaseModel):
    name: Short
    kind: Literal["headquarters", "branch", "office", "store", "warehouse", "factory", "remote", "other"] = "office"
    address: Text | None = None
    city: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] | None = None
    country: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] | None = None
    timezone: str | None = None
    is_primary: bool = False

    _tz = field_validator("timezone")(validate_timezone)


class LocationOut(ORM, LocationIn):
    id: uuid.UUID
    created_at: datetime


class DepartmentIn(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    description: Text | None = None
    head_name: Short | None = None


class DepartmentOut(ORM, DepartmentIn):
    id: uuid.UUID
    created_at: datetime


class JobRoleIn(BaseModel):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
    department_id: uuid.UUID | None = None
    description: Text | None = None
    headcount: Annotated[int, Field(ge=0, le=1_000_000)] | None = None


class JobRoleOut(ORM, JobRoleIn):
    id: uuid.UUID
    created_at: datetime


class OfferingIn(BaseModel):
    name: Short
    kind: Literal["product", "service"] = "product"
    description: Text | None = None
    sku: Annotated[str, StringConstraints(strip_whitespace=True, max_length=80)] | None = None
    pricing_note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] | None = None


class OfferingOut(ORM, OfferingIn):
    id: uuid.UUID
    created_at: datetime


class ObjectiveIn(BaseModel):
    title: Short
    description: Text | None = None
    kpi_name: Annotated[str, StringConstraints(strip_whitespace=True, max_length=160)] | None = None
    kpi_target: Decimal | None = None
    kpi_unit: Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)] | None = None
    target_date: date | None = None
    department_id: uuid.UUID | None = None
    status: Literal["active", "achieved", "dropped"] = "active"


class ObjectiveOut(ORM, ObjectiveIn):
    id: uuid.UUID
    created_at: datetime


class ProcessIn(BaseModel):
    name: Short
    description: Text | None = None
    department_id: uuid.UUID | None = None
    frequency: Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)] | None = None
    approval_procedure: Text | None = None


class ProcessOut(ORM, ProcessIn):
    id: uuid.UUID
    created_at: datetime


class SoftwareIn(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
    category: Literal["accounting", "crm", "erp", "inventory", "pos", "hr", "payroll", "marketing", "support",
                      "project_management", "communication", "ecommerce", "spreadsheet", "other"] = "other"
    notes: Text | None = None
    integration_wanted: bool = False


class SoftwareOut(ORM, SoftwareIn):
    id: uuid.UUID
    created_at: datetime


class ChallengeIn(BaseModel):
    title: Short
    description: Text | None = None
    severity: Literal["low", "medium", "high"] = "medium"
    department_id: uuid.UUID | None = None


class ChallengeOut(ORM, ChallengeIn):
    id: uuid.UUID
    created_at: datetime


LocationPatch = _partial(LocationIn, "LocationPatch")
DepartmentPatch = _partial(DepartmentIn, "DepartmentPatch")
JobRolePatch = _partial(JobRoleIn, "JobRolePatch")
OfferingPatch = _partial(OfferingIn, "OfferingPatch")
ObjectivePatch = _partial(ObjectiveIn, "ObjectivePatch")
ProcessPatch = _partial(ProcessIn, "ProcessPatch")
SoftwarePatch = _partial(SoftwareIn, "SoftwarePatch")
ChallengePatch = _partial(ChallengeIn, "ChallengePatch")
