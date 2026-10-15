import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from abos.core import ratelimit
from abos.core.config import get_settings
from abos.core.db import get_db
from abos.core.errors import AppError, forbidden
from abos.core.security import hash_token
from abos.core.tenancy import set_tenant
from abos.identity.models import Organization, OrganizationMembership, User, UserSession
from abos.identity.permissions import org_role_has


@dataclass
class ClientMeta:
    ip: str | None
    user_agent: str | None


def client_meta(request: Request) -> ClientMeta:
    ua = request.headers.get("user-agent")
    return ClientMeta(ip=request.client.host if request.client else None, user_agent=ua[:400] if ua else None)


@dataclass
class AuthContext:
    user: User
    session: UserSession
    meta: ClientMeta


@dataclass
class OrgContext:
    user: User
    organization: Organization
    membership: OrganizationMembership
    meta: ClientMeta

    @property
    def org_id(self) -> uuid.UUID:
        return self.organization.id

    @property
    def role(self) -> str:
        return self.membership.role

    def can(self, permission: str) -> bool:
        return org_role_has(self.role, permission)


def current_auth(request: Request, db: Session = Depends(get_db)) -> AuthContext:
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise AppError(401, "unauthenticated", "Sign in required")
    now = datetime.now(UTC)
    session = db.scalar(select(UserSession).where(UserSession.token_hash == hash_token(token)))
    if session is None or session.revoked_at is not None or session.expires_at <= now:
        raise AppError(401, "unauthenticated", "Session expired or revoked")
    user = session.user
    if user.status != "active":
        raise AppError(403, "account_suspended", "This account is suspended")
    if now - session.last_seen_at > timedelta(minutes=5):
        session.last_seen_at = now
        db.commit()
    return AuthContext(user=user, session=session, meta=client_meta(request))


def per_user(limit_name: str):
    """Dependency: rate-limit by signed-in user."""

    def _dep(auth: AuthContext = Depends(current_auth)) -> None:
        ratelimit.hit(limit_name, str(auth.user.id), scope="user")

    return Depends(_dep)


def require_org_member(
    auth: AuthContext = Depends(current_auth),
    db: Session = Depends(get_db),
    x_org_id: str | None = Header(default=None),
) -> OrgContext:
    """Resolve the active organization from X-Org-Id and verify membership server-side (never trust the header)."""
    if not x_org_id:
        raise AppError(400, "org_required", "X-Org-Id header is required")
    try:
        org_id = uuid.UUID(x_org_id)
    except ValueError as exc:
        raise AppError(400, "org_required", "X-Org-Id must be a UUID") from exc
    membership = db.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == org_id,
            OrganizationMembership.user_id == auth.user.id,
        )
    )
    # Same response for "no such org" and "not a member" so org ids can't be probed.
    if membership is None or membership.organization.status != "active":
        raise forbidden("You are not a member of this organization")
    # Second layer behind this check: Postgres RLS only shows this org's tenant rows from here on (ADR-003).
    set_tenant(db, org_id)
    return OrgContext(user=auth.user, organization=membership.organization, membership=membership, meta=auth.meta)


def ai_work():
    """Dependency for endpoints that start model calls or worker jobs (generation, simulations, runs, reports,
    ingestion, extraction, evaluations): limited per user and per workspace, so one account or one tenant can't
    exhaust the shared worker or the model budget. `tests/test_security_surface.py` lists the routes that need it."""

    def _dep(ctx: OrgContext = Depends(require_org_member)) -> None:
        ratelimit.hit("ai_work_user", str(ctx.user.id), scope="user")
        ratelimit.hit("ai_work_org", str(ctx.org_id), scope="organization")

    return Depends(_dep)


def require_org_permission(permission: str):
    def _dep(ctx: OrgContext = Depends(require_org_member)) -> OrgContext:
        if not ctx.can(permission):
            raise forbidden()
        return ctx

    return _dep
