"""Phase 7 security review, as tests that walk the whole API surface (SPEC §6, §10 Phase 7).

A new route can't ship without: authentication (unless deliberately public), a named permission on every workspace
route, a rate limit on work that costs model calls or worker time, and the same denial for anonymous callers,
non-members and under-privileged members. These tests enumerate the routes from the app, so they cover routes
added later too.
"""

import inspect
import re
import uuid

import pytest
from fastapi.routing import APIRoute

from abos.core.config import get_settings
from abos.identity.permissions import ORG_PERMISSIONS
from abos.main import app
from tests.conftest import join, new_client

PUBLIC = {  # reachable without a session, each with its own abuse protection
    ("GET", "/api/health"), ("GET", "/api/health/ready"), ("GET", "/api/metrics"),
    ("POST", "/api/v1/auth/register"), ("POST", "/api/v1/auth/login"), ("POST", "/api/v1/auth/verify-email"),
    ("POST", "/api/v1/auth/password-reset/request"), ("POST", "/api/v1/auth/password-reset/confirm"),
}
MEMBER_ONLY = {("GET", "/api/v1/org")}  # any member may read the workspace's own name/status
# Non-GET routes behind a read-level permission: they touch only the caller's own rows, or are reads whose query
# travels in the body.
OWN_ROWS_WRITES = {
    ("POST", "/api/v1/notifications/{notification_id}/read"), ("POST", "/api/v1/notifications/read-all"),
    ("PUT", "/api/v1/notifications/preferences"), ("POST", "/api/v1/knowledge/search"),
}
AI_WORK = {  # routes that start model calls or worker jobs → ai_work() (per user + per workspace)
    ("POST", "/api/v1/documents"), ("POST", "/api/v1/documents/url"), ("POST", "/api/v1/documents/{doc_id}/versions"),
    ("POST", "/api/v1/documents/{doc_id}/retry"), ("POST", "/api/v1/documents/{doc_id}/reprocess"),
    ("POST", "/api/v1/knowledge/search"), ("POST", "/api/v1/knowledge/evals/runs"),
    ("POST", "/api/v1/interview/generate"), ("POST", "/api/v1/rules/extract"),
    ("POST", "/api/v1/agents/{instance_id}/config/generate"), ("POST", "/api/v1/agents/{instance_id}/simulations"),
    ("POST", "/api/v1/workflows"), ("POST", "/api/v1/reports/generate"),
}
OTHER_LIMITED = {  # their own, stricter limits
    ("POST", "/api/v1/knowledge/ask"): "ask_user", ("POST", "/api/v1/org/exports"): "export_user",
    ("POST", "/api/v1/org/deletion"): "sensitive_user", ("POST", "/api/v1/orgs"): "sensitive_user",
}


def _routes() -> list[APIRoute]:
    out: list[APIRoute] = []

    def walk(routes):
        for r in routes:
            if type(r).__name__ == "_IncludedRouter":
                walk(r.original_router.routes)
            elif isinstance(r, APIRoute):
                out.append(r)

    walk(app.routes)
    return out


def _calls(route: APIRoute) -> list:
    found = []

    def walk(dep):
        for sub in dep.dependencies:
            found.append(sub.call)
            walk(sub)

    walk(route.dependant)
    return found


def _named(route: APIRoute, qualname: str) -> list:
    return [c for c in _calls(route) if getattr(c, "__qualname__", "") == qualname]


def _permission(route: APIRoute) -> str | None:
    deps = _named(route, "require_org_permission.<locals>._dep")
    return inspect.getclosurevars(deps[0]).nonlocals["permission"] if deps else None


def _limits(route: APIRoute) -> set[str]:
    names = set()
    for call in _named(route, "per_user.<locals>._dep") + _named(route, "per_ip.<locals>._dep"):
        names.add(inspect.getclosurevars(call).nonlocals["limit_name"])
    if _named(route, "ai_work.<locals>._dep"):
        names.add("ai_work")
    return names


ROUTES = [(m, r.path, r) for r in _routes() for m in sorted(r.methods)]


def test_route_inventory_is_complete():
    keys = {(m, p) for m, p, _ in ROUTES}
    assert len(keys) > 150
    for listed in PUBLIC | MEMBER_ONLY | OWN_ROWS_WRITES | AI_WORK | set(OTHER_LIMITED):
        assert listed in keys, f"stale allowlist entry {listed}"


@pytest.mark.parametrize(("method", "path", "route"), ROUTES, ids=[f"{m} {p}" for m, p, _ in ROUTES])
def test_every_route_declares_authentication_and_permission(method, path, route):
    calls = {getattr(c, "__qualname__", "") for c in _calls(route)}
    if (method, path) in PUBLIC:
        assert "current_auth" not in calls
        return
    assert "current_auth" in calls, "authenticated routes must depend on current_auth"
    if "require_org_member" not in calls:
        # Account-level routes act on the caller's own user/session only and never take an org id.
        assert path.startswith(("/api/v1/auth/", "/api/v1/orgs", "/api/v1/company/timezones")), path
        return
    permission = _permission(route)
    if (method, path) in MEMBER_ONLY:
        assert permission is None
        return
    assert permission is not None, "workspace routes check a named permission (identity/permissions.py)"
    assert permission in ORG_PERMISSIONS["owner"], f"unknown permission {permission!r}"
    if method != "GET" and (method, path) not in OWN_ROWS_WRITES:
        assert not permission.endswith(".read"), f"{method} {path} changes data behind a read permission"


@pytest.mark.parametrize(("method", "path", "route"), ROUTES, ids=[f"{m} {p}" for m, p, _ in ROUTES])
def test_costly_routes_are_rate_limited(method, path, route):
    limits = _limits(route)
    if (method, path) in AI_WORK:
        assert "ai_work" in limits
    elif (method, path) in OTHER_LIMITED:
        assert OTHER_LIMITED[(method, path)] in limits
    if path.startswith("/api/v1/auth/") and method == "POST" and path not in (
            "/api/v1/auth/logout", "/api/v1/auth/verify-email"):
        assert limits, f"{path}: credential endpoints are rate limited"


def _concrete(path: str) -> str:
    return re.sub(r"\{(\w+)\}", lambda m: "0" if m.group(1) == "index" else str(uuid.uuid4()), path)


def _call(client, method: str, path: str, org_id: str | None):
    headers = {"X-Org-Id": org_id} if org_id else {}
    kwargs = {"json": {}} if method in ("POST", "PUT", "PATCH") else {}
    return client.request(method, _concrete(path), headers=headers, **kwargs)


ORG_ROUTES = [(m, p) for m, p, r in ROUTES
              if "require_org_member" in {getattr(c, "__qualname__", "") for c in _calls(r)}]


def test_every_workspace_route_denies_anonymous_and_non_members(owner, rival):
    anonymous = new_client()
    for method, path in ORG_ROUTES:
        r = _call(anonymous, method, path, owner.org_id)
        assert r.status_code == 401, (method, path, r.status_code)
        # A member of another workspace using this workspace's id is refused before anything else happens.
        r = _call(rival.client, method, path, owner.org_id)
        assert r.status_code == 403, (method, path, r.status_code, r.text[:200])
        assert r.json()["error"]["code"] == "forbidden"


def test_every_workspace_route_enforces_its_permission_for_a_viewer(owner):
    viewer = join(owner, "viewer@acme.example.com", "viewer")
    allowed = ORG_PERMISSIONS["viewer"]
    by_key = {(m, p): r for m, p, r in ROUTES}
    checked = 0
    for method, path in ORG_ROUTES:
        permission = _permission(by_key[(method, path)])
        if permission is None or permission in allowed:
            continue
        r = _call(viewer.client, method, path, owner.org_id)
        assert r.status_code == 403, (method, path, permission, r.status_code)
        checked += 1
    assert checked > 80


def test_ai_work_is_limited_per_user_and_per_workspace(owner, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "rl_ai_work_user", "2/3600")
    monkeypatch.setattr(s, "rl_ai_work_org", "3/3600")
    for _ in range(2):
        assert owner.post("/api/v1/knowledge/search", json={"query": "refund policy"}).status_code == 200
    r = owner.post("/api/v1/knowledge/search", json={"query": "refund policy"})
    assert r.status_code == 429 and r.headers["Retry-After"]
    assert r.json()["error"]["details"]["scope"] == "user"
    # A colleague has their own allowance, but the workspace's shared one runs out next.
    manager = join(owner, "manager@acme.example.com", "manager")
    assert manager.post("/api/v1/knowledge/search", json={"query": "refund"}).status_code == 200
    r = manager.post("/api/v1/knowledge/search", json={"query": "refund"})
    assert r.status_code == 429 and r.json()["error"]["details"]["scope"] == "organization"


def test_security_headers_on_every_kind_of_response(owner):
    for r in (owner.get("/api/v1/org"), owner.get("/api/v1/nope"), new_client().get("/api/v1/auth/me"),
              owner.client.post("/api/v1/org/members", json={}, headers={"X-Requested-With": ""})):
        assert r.headers["X-Content-Type-Options"] == "nosniff"
        assert r.headers["X-Frame-Options"] == "DENY"
        assert "default-src 'none'" in r.headers["Content-Security-Policy"]
        assert r.headers["Cache-Control"] == "no-store"
        assert r.headers["X-Request-Id"]


def test_production_settings_refuse_unsafe_values():
    from pydantic import ValidationError

    from abos.core.config import Settings

    safe = dict(env="production", cookie_secure=True, session_cookie_name="__Host-abos",
                database_url="postgresql+psycopg://abos:s3cret@db/abos", app_base_url="https://app.example.com",
                mailer="smtp", smtp_host="smtp.example.com", llm_provider="anthropic", anthropic_api_key="k",
                embedding_provider="voyage", embedding_api_key="k", sms_provider="none", storage_backend="s3",
                s3_bucket="b", jobs_eager=False)
    Settings(**safe)  # a complete production configuration is accepted
    for bad in ({"cookie_secure": False}, {"session_cookie_name": "abos"}, {"llm_provider": "dev"},
                {"embedding_provider": "hash"}, {"sms_provider": "dev"}, {"storage_backend": "local"},
                {"jobs_eager": True}, {"rate_limits_enabled": False}, {"mailer": "dev_outbox"},
                {"app_base_url": "http://app.example.com"}, {"error_reporter": "sentry"},
                {"database_url": "postgresql+psycopg://abos:abos_dev_password@db/abos"}):
        with pytest.raises(ValidationError):
            Settings(**{**safe, **bad})
    # Secrets (DB password, SMTP password, API keys) never appear in the settings' repr (logs, tracebacks).
    text = repr(Settings(**{**safe, "smtp_password": "s3cret", "anthropic_api_key": "s3cret"}))
    assert "s3cret" not in text
