import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from abos.audit import service as audit
from abos.core import ratelimit
from abos.core.config import get_settings
from abos.core.errors import AppError, conflict, forbidden, not_found, too_many
from abos.core.security import hash_password, hash_token, needs_rehash, new_token, verify_password
from abos.core.tenancy import set_tenant
from abos.identity import mailer
from abos.identity.deps import ClientMeta, OrgContext
from abos.identity.models import (
    AuthenticationEvent,
    AuthToken,
    Organization,
    OrganizationMembership,
    User,
    UserSession,
)
from abos.identity.permissions import ORG_PERMISSIONS
from abos.identity.schemas import MembershipOut, MeOut, OrgOut, RegisterIn, UserOut


def _now() -> datetime:
    return datetime.now(UTC)


def _auth_event(db: Session, event_type: str, meta: ClientMeta, *, user: User | None = None,
                email: str | None = None) -> None:
    db.add(AuthenticationEvent(
        user_id=user.id if user else None,
        email=(email or (user.email if user else None)),
        event_type=event_type,
        ip=meta.ip,
        user_agent=meta.user_agent,
    ))


def _unique_slug(db: Session, name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60] or "org"
    slug = base
    while db.scalar(select(Organization.id).where(Organization.slug == slug)):
        slug = f"{base}-{secrets.token_hex(3)}"
    return slug


# ---- sessions & tokens -------------------------------------------------------------------------

def create_session(db: Session, user: User, meta: ClientMeta) -> str:
    token = new_token()
    db.add(UserSession(
        user_id=user.id,
        token_hash=hash_token(token),
        expires_at=_now() + timedelta(hours=get_settings().session_ttl_hours),
        ip=meta.ip,
        user_agent=meta.user_agent,
    ))
    return token


def revoke_all_sessions(db: Session, user_id: uuid.UUID, *, except_id: uuid.UUID | None = None) -> None:
    stmt = update(UserSession).where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
    if except_id:
        stmt = stmt.where(UserSession.id != except_id)
    db.execute(stmt.values(revoked_at=_now()))


def _issue_token(db: Session, user: User, purpose: str, ttl: timedelta) -> str:
    token = new_token()
    db.add(AuthToken(user_id=user.id, purpose=purpose, token_hash=hash_token(token), expires_at=_now() + ttl))
    return token


def _consume_token(db: Session, token: str, purpose: str) -> AuthToken:
    record = db.scalar(
        select(AuthToken).where(AuthToken.token_hash == hash_token(token), AuthToken.purpose == purpose)
        .with_for_update()
    )
    if record is None or record.used_at is not None or record.expires_at <= _now():
        raise AppError(400, "invalid_token", "This link is invalid or has expired")
    record.used_at = _now()
    return record


def _send_verification(db: Session, user: User) -> None:
    token = _issue_token(db, user, "verify_email", timedelta(hours=get_settings().email_verify_ttl_hours))
    link = f"{get_settings().app_base_url}/verify-email?token={token}"
    mailer.send(db, user.email, "Verify your AI Business OS email",
                f"Hello {user.full_name},\n\nConfirm your email address:\n{link}\n")


# ---- organizations -----------------------------------------------------------------------------

def _create_org(db: Session, owner: User, name: str, job_title: str | None, meta: ClientMeta) -> Organization:
    """New workspace with `owner` as its first member and Owner (SPEC step 1). Caller commits."""
    from abos.company import service as company  # local: company depends on identity

    org = Organization(name=name, slug=_unique_slug(db, name))
    db.add(org)
    db.flush()
    set_tenant(db, org.id)  # everything below is tenant data (RLS, ADR-003)
    db.add(OrganizationMembership(organization_id=org.id, user_id=owner.id, role="owner", job_title=job_title))
    company.create_profile(db, org.id, name)
    audit.record(db, "org.created", actor_id=owner.id, org_id=org.id, target_type="organization",
                 target_id=org.id, data={"name": name, "job_title": job_title}, ip=meta.ip)
    return org


def create_org(db: Session, user: User, name: str, job_title: str | None, meta: ClientMeta) -> Organization:
    org = _create_org(db, user, name, job_title, meta)
    db.commit()
    return org


# ---- registration & login ----------------------------------------------------------------------

def register(db: Session, data: RegisterIn, meta: ClientMeta) -> tuple[User, str]:
    email = data.email.lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise conflict("An account with this email already exists")
    user = User(email=email, password_hash=hash_password(data.password), full_name=data.full_name)
    db.add(user)
    db.flush()
    _create_org(db, user, data.organization_name, data.job_title, meta)
    _auth_event(db, "register", meta, user=user)
    _send_verification(db, user)
    token = create_session(db, user, meta)
    db.commit()
    return user, token


def _recent_failures(db: Session, email: str) -> int:
    s = get_settings()
    since = _now() - timedelta(minutes=s.login_failure_window_minutes)
    return db.scalar(
        select(func.count()).select_from(AuthenticationEvent).where(
            AuthenticationEvent.email == email,
            AuthenticationEvent.event_type == "login_failure",
            AuthenticationEvent.created_at >= since,
        )
    ) or 0


def login(db: Session, email: str, password: str, meta: ClientMeta) -> tuple[User, str]:
    email = email.lower()
    s = get_settings()
    if _recent_failures(db, email) >= s.login_failure_limit:
        raise too_many("too_many_attempts", "Too many failed sign-in attempts. Try again later.",
                       s.login_failure_window_minutes * 60, "account")
    user = db.scalar(select(User).where(User.email == email))
    if not verify_password(user.password_hash if user else None, password) or user is None:
        _auth_event(db, "login_failure", meta, user=user, email=email)
        db.commit()
        raise AppError(401, "invalid_credentials", "Email or password is incorrect")
    if user.status != "active":
        _auth_event(db, "login_blocked_suspended", meta, user=user)
        db.commit()
        raise AppError(403, "account_suspended", "This account is suspended")
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    user.last_login_at = _now()
    _auth_event(db, "login_success", meta, user=user)
    token = create_session(db, user, meta)
    db.commit()
    return user, token


def logout(db: Session, session: UserSession, meta: ClientMeta) -> None:
    session.revoked_at = _now()
    _auth_event(db, "logout", meta, user=session.user)
    db.commit()


def verify_email(db: Session, token: str, meta: ClientMeta) -> User:
    record = _consume_token(db, token, "verify_email")
    user = db.get(User, record.user_id)
    assert user is not None
    user.email_verified_at = user.email_verified_at or _now()
    _auth_event(db, "email_verified", meta, user=user)
    db.commit()
    return user


def resend_verification(db: Session, user: User) -> None:
    if user.email_verified_at is None:
        _send_verification(db, user)
        db.commit()


def request_password_reset(db: Session, email: str, meta: ClientMeta) -> None:
    """Always succeeds from the caller's view so account existence isn't revealed."""
    email = email.lower()
    ratelimit.hit("password_reset_email", email, scope="email")
    user = db.scalar(select(User).where(User.email == email))
    _auth_event(db, "password_reset_requested", meta, user=user, email=email)
    if user is not None and user.status == "active":
        token = _issue_token(db, user, "reset_password",
                             timedelta(minutes=get_settings().password_reset_ttl_minutes))
        link = f"{get_settings().app_base_url}/reset-password?token={token}"
        mailer.send(db, user.email, "Reset your AI Business OS password",
                    f"A password reset was requested for your account.\n\n{link}\n\n"
                    "If you did not request this, you can ignore this email.\n")
    db.commit()


def confirm_password_reset(db: Session, token: str, new_password: str, meta: ClientMeta) -> None:
    record = _consume_token(db, token, "reset_password")
    user = db.get(User, record.user_id)
    assert user is not None
    user.password_hash = hash_password(new_password)
    revoke_all_sessions(db, user.id)
    _auth_event(db, "password_reset_completed", meta, user=user)
    db.commit()


def change_password(db: Session, user: User, session: UserSession, current: str, new: str,
                    meta: ClientMeta) -> None:
    if not verify_password(user.password_hash, current):
        raise AppError(400, "invalid_credentials", "Current password is incorrect")
    user.password_hash = hash_password(new)
    revoke_all_sessions(db, user.id, except_id=session.id)
    _auth_event(db, "password_changed", meta, user=user)
    db.commit()


def me(user: User) -> MeOut:
    memberships = [
        MembershipOut(
            organization=OrgOut.model_validate(m.organization),
            role=m.role,
            job_title=m.job_title,
            permissions=sorted(ORG_PERMISSIONS[m.role]),
        )
        for m in sorted(user.memberships, key=lambda m: m.created_at)
        if m.organization.status == "active"
    ]
    return MeOut(user=UserOut.model_validate(user), memberships=memberships)


def list_sessions(db: Session, user: User) -> list[UserSession]:
    return list(db.scalars(
        select(UserSession).where(
            UserSession.user_id == user.id, UserSession.revoked_at.is_(None), UserSession.expires_at > _now()
        ).order_by(UserSession.last_seen_at.desc())
    ))


def revoke_session(db: Session, user: User, session_id: uuid.UUID, meta: ClientMeta) -> None:
    session = db.get(UserSession, session_id)
    if session is None or session.user_id != user.id:
        raise not_found("Session")
    session.revoked_at = session.revoked_at or _now()
    _auth_event(db, "session_revoked", meta, user=user)
    db.commit()


# ---- organization membership -------------------------------------------------------------------

def update_org(db: Session, ctx: OrgContext, name: str) -> Organization:
    previous, ctx.organization.name = ctx.organization.name, name
    audit.record(db, "org.updated", actor_id=ctx.user.id, org_id=ctx.org_id, target_type="organization",
                 target_id=ctx.org_id, data={"from": previous, "to": name}, ip=ctx.meta.ip)
    db.commit()
    return ctx.organization


def list_members(db: Session, org_id: uuid.UUID) -> list[OrganizationMembership]:
    return list(db.scalars(
        select(OrganizationMembership).where(OrganizationMembership.organization_id == org_id)
        .order_by(OrganizationMembership.created_at)
    ))


def _guard_owner_change(ctx: OrgContext, *roles: str | None) -> None:
    if "owner" in roles and not ctx.can("org.members.manage_owners"):
        raise forbidden("Only owners can grant or remove the owner role")


def add_member(db: Session, ctx: OrgContext, email: str, role: str, job_title: str | None) -> OrganizationMembership:
    _guard_owner_change(ctx, role)
    user = db.scalar(select(User).where(User.email == email.lower()))
    if user is None:
        # Email invitations for unregistered users are a later feature; be explicit rather than silent.
        raise AppError(404, "user_not_found", "No registered user with this email. Ask them to sign up first.")
    exists = db.scalar(select(OrganizationMembership.id).where(
        OrganizationMembership.organization_id == ctx.org_id, OrganizationMembership.user_id == user.id))
    if exists:
        raise conflict("This user is already a member")
    membership = OrganizationMembership(organization_id=ctx.org_id, user_id=user.id, role=role, job_title=job_title)
    db.add(membership)
    audit.record(db, "org.member_added", actor_id=ctx.user.id, org_id=ctx.org_id, target_type="user",
                 target_id=user.id, data={"role": role, "job_title": job_title}, ip=ctx.meta.ip)
    db.commit()
    return membership


def _membership(db: Session, org_id: uuid.UUID, user_id: uuid.UUID) -> OrganizationMembership:
    m = db.scalar(select(OrganizationMembership).where(
        OrganizationMembership.organization_id == org_id, OrganizationMembership.user_id == user_id
    ).with_for_update())
    if m is None:
        raise not_found("Member")
    return m


def _owner_count(db: Session, org_id: uuid.UUID) -> int:
    return db.scalar(select(func.count()).select_from(OrganizationMembership).where(
        OrganizationMembership.organization_id == org_id, OrganizationMembership.role == "owner")) or 0


def update_member(db: Session, ctx: OrgContext, user_id: uuid.UUID, role: str | None, job_title: str | None,
                  clear_job_title: bool) -> OrganizationMembership:
    m = _membership(db, ctx.org_id, user_id)
    changes: dict = {}
    if role is not None and role != m.role:
        _guard_owner_change(ctx, role, m.role)
        if m.role == "owner" and _owner_count(db, ctx.org_id) <= 1:
            raise conflict("An organization must keep at least one owner")
        changes["role"] = {"from": m.role, "to": role}
        m.role = role
    if clear_job_title or (job_title is not None and job_title != m.job_title):
        new_title = None if clear_job_title else job_title
        changes["job_title"] = {"from": m.job_title, "to": new_title}
        m.job_title = new_title
    if changes:
        audit.record(db, "org.member_updated", actor_id=ctx.user.id, org_id=ctx.org_id, target_type="user",
                     target_id=user_id, data=changes, ip=ctx.meta.ip)
    db.commit()
    return m


def remove_member(db: Session, ctx: OrgContext, user_id: uuid.UUID) -> None:
    m = _membership(db, ctx.org_id, user_id)
    _guard_owner_change(ctx, m.role)
    if m.role == "owner" and _owner_count(db, ctx.org_id) <= 1:
        raise conflict("An organization must keep at least one owner")
    db.delete(m)
    audit.record(db, "org.member_removed", actor_id=ctx.user.id, org_id=ctx.org_id, target_type="user",
                 target_id=user_id, data={"role": m.role}, ip=ctx.meta.ip)
    db.commit()
