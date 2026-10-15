import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

Password = Annotated[str, Field(min_length=10, max_length=128)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
JobTitle = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
OrgRole = Literal["owner", "admin", "manager", "member", "viewer"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RegisterIn(BaseModel):
    email: EmailStr
    password: Password
    full_name: Name
    organization_name: Name
    job_title: JobTitle | None = None  # e.g. "CEO" — a business title, not a permission


class LoginIn(BaseModel):
    email: EmailStr
    password: Annotated[str, Field(min_length=1, max_length=128)]


class TokenIn(BaseModel):
    token: Annotated[str, Field(min_length=10, max_length=200)]


class EmailIn(BaseModel):
    email: EmailStr


class PasswordResetConfirmIn(TokenIn):
    new_password: Password


class PasswordChangeIn(BaseModel):
    current_password: Annotated[str, Field(min_length=1, max_length=128)]
    new_password: Password


class UserOut(ORM):
    id: uuid.UUID
    email: str
    full_name: str
    status: str
    email_verified_at: datetime | None
    created_at: datetime


class OrgOut(ORM):
    id: uuid.UUID
    name: str
    slug: str
    status: str
    created_at: datetime
    deletion_scheduled_at: datetime | None = None


class MembershipOut(BaseModel):
    organization: OrgOut
    role: str
    job_title: str | None
    permissions: list[str]


class MeOut(BaseModel):
    user: UserOut
    memberships: list[MembershipOut]


class OrgCreateIn(BaseModel):
    name: Name
    job_title: JobTitle | None = None


class OrgUpdateIn(BaseModel):
    name: Name


class MemberOut(BaseModel):
    user_id: uuid.UUID
    email: str
    full_name: str
    role: str
    job_title: str | None
    status: str
    joined_at: datetime


class AddMemberIn(BaseModel):
    email: EmailStr
    role: OrgRole
    job_title: JobTitle | None = None


class MemberUpdateIn(BaseModel):
    role: OrgRole | None = None
    job_title: JobTitle | None = None
    clear_job_title: bool = False


class SessionOut(ORM):
    id: uuid.UUID
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    ip: str | None
    user_agent: str | None
    current: bool = False
