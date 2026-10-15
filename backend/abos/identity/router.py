import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from abos.core.config import get_settings
from abos.core.db import get_db
from abos.core.ratelimit import per_ip
from abos.identity import service
from abos.identity.deps import (
    AuthContext,
    ClientMeta,
    OrgContext,
    client_meta,
    current_auth,
    per_user,
    require_org_member,
    require_org_permission,
)
from abos.identity.schemas import (
    AddMemberIn,
    EmailIn,
    LoginIn,
    MemberOut,
    MemberUpdateIn,
    MeOut,
    OrgCreateIn,
    OrgOut,
    OrgUpdateIn,
    PasswordChangeIn,
    PasswordResetConfirmIn,
    RegisterIn,
    SessionOut,
    TokenIn,
    UserOut,
)

auth_router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
orgs_router = APIRouter(prefix="/api/v1/orgs", tags=["organization"])
org_router = APIRouter(prefix="/api/v1/org", tags=["organization"])


def _set_cookie(response: Response, token: str) -> None:
    s = get_settings()
    response.set_cookie(
        s.session_cookie_name, token, max_age=s.session_ttl_hours * 3600,
        httponly=True, secure=s.cookie_secure, samesite="lax", path="/",
    )


def _clear_cookie(response: Response) -> None:
    s = get_settings()
    response.delete_cookie(s.session_cookie_name, path="/", httponly=True, secure=s.cookie_secure, samesite="lax")


@auth_router.post("/register", response_model=MeOut, status_code=201, dependencies=[per_ip("register_ip")])
def register(data: RegisterIn, response: Response, db: Session = Depends(get_db),
             meta: ClientMeta = Depends(client_meta)):
    user, token = service.register(db, data, meta)
    _set_cookie(response, token)
    db.refresh(user)
    return service.me(user)


@auth_router.post("/login", response_model=MeOut, dependencies=[per_ip("login_ip")])
def login(data: LoginIn, response: Response, db: Session = Depends(get_db),
          meta: ClientMeta = Depends(client_meta)):
    user, token = service.login(db, data.email, data.password, meta)
    _set_cookie(response, token)
    return service.me(user)


@auth_router.post("/logout", status_code=204)
def logout(auth: AuthContext = Depends(current_auth), db: Session = Depends(get_db)):
    service.logout(db, auth.session, auth.meta)
    response = Response(status_code=204)
    _clear_cookie(response)
    return response


@auth_router.get("/me", response_model=MeOut)
def me(auth: AuthContext = Depends(current_auth)):
    return service.me(auth.user)


@auth_router.post("/verify-email", response_model=UserOut)
def verify_email(data: TokenIn, db: Session = Depends(get_db), meta: ClientMeta = Depends(client_meta)):
    return service.verify_email(db, data.token, meta)


@auth_router.post("/verify-email/resend", status_code=202, dependencies=[per_user("verify_resend_user")])
def resend_verification(auth: AuthContext = Depends(current_auth), db: Session = Depends(get_db)):
    service.resend_verification(db, auth.user)
    return {"status": "accepted"}


@auth_router.post("/password-reset/request", status_code=202, dependencies=[per_ip("password_reset_ip")])
def password_reset_request(data: EmailIn, db: Session = Depends(get_db),
                           meta: ClientMeta = Depends(client_meta)):
    service.request_password_reset(db, data.email, meta)
    return {"status": "accepted"}


@auth_router.post("/password-reset/confirm", status_code=204, dependencies=[per_ip("password_reset_ip")])
def password_reset_confirm(data: PasswordResetConfirmIn, db: Session = Depends(get_db),
                           meta: ClientMeta = Depends(client_meta)):
    service.confirm_password_reset(db, data.token, data.new_password, meta)
    return Response(status_code=204)


@auth_router.post("/password", status_code=204, dependencies=[per_user("sensitive_user")])
def change_password(data: PasswordChangeIn, auth: AuthContext = Depends(current_auth),
                    db: Session = Depends(get_db)):
    service.change_password(db, auth.user, auth.session, data.current_password, data.new_password, auth.meta)
    return Response(status_code=204)


@auth_router.get("/sessions", response_model=list[SessionOut])
def sessions(auth: AuthContext = Depends(current_auth), db: Session = Depends(get_db)):
    out = []
    for s in service.list_sessions(db, auth.user):
        item = SessionOut.model_validate(s)
        item.current = s.id == auth.session.id
        out.append(item)
    return out


@auth_router.delete("/sessions/{session_id}", status_code=204)
def revoke_session(session_id: uuid.UUID, auth: AuthContext = Depends(current_auth),
                   db: Session = Depends(get_db)):
    service.revoke_session(db, auth.user, session_id, auth.meta)
    return Response(status_code=204)


# ---- organizations -----------------------------------------------------------------------------

@orgs_router.post("", response_model=OrgOut, status_code=201, dependencies=[per_user("sensitive_user")])
def create_org(data: OrgCreateIn, auth: AuthContext = Depends(current_auth), db: Session = Depends(get_db)):
    """Create another workspace. The caller becomes its owner."""
    return service.create_org(db, auth.user, data.name, data.job_title, auth.meta)


def _member_out(m) -> MemberOut:
    return MemberOut(user_id=m.user_id, email=m.user.email, full_name=m.user.full_name, role=m.role,
                     job_title=m.job_title, status=m.user.status, joined_at=m.created_at)


@org_router.get("", response_model=OrgOut)
def get_org(ctx: OrgContext = Depends(require_org_member)):
    return ctx.organization


@org_router.patch("", response_model=OrgOut)
def update_org(data: OrgUpdateIn, ctx: OrgContext = Depends(require_org_permission("org.manage")),
               db: Session = Depends(get_db)):
    return service.update_org(db, ctx, data.name)


@org_router.get("/members", response_model=list[MemberOut])
def members(ctx: OrgContext = Depends(require_org_permission("org.read")), db: Session = Depends(get_db)):
    return [_member_out(m) for m in service.list_members(db, ctx.org_id)]


@org_router.post("/members", response_model=MemberOut, status_code=201)
def add_member(data: AddMemberIn, ctx: OrgContext = Depends(require_org_permission("org.members.manage")),
               db: Session = Depends(get_db)):
    m = service.add_member(db, ctx, data.email, data.role, data.job_title)
    db.refresh(m)
    return _member_out(m)


@org_router.patch("/members/{user_id}", response_model=MemberOut)
def update_member(user_id: uuid.UUID, data: MemberUpdateIn,
                  ctx: OrgContext = Depends(require_org_permission("org.members.manage")),
                  db: Session = Depends(get_db)):
    return _member_out(service.update_member(db, ctx, user_id, data.role, data.job_title, data.clear_job_title))


@org_router.delete("/members/{user_id}", status_code=204)
def remove_member(user_id: uuid.UUID, ctx: OrgContext = Depends(require_org_permission("org.members.manage")),
                  db: Session = Depends(get_db)):
    service.remove_member(db, ctx, user_id)
    return Response(status_code=204)
