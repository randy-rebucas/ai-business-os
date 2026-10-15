from sqlalchemy import select

from abos.identity.models import EmailOutbox, OrganizationMembership
from tests.conftest import PASSWORD, last_email_token, new_client, register


def test_register_creates_workspace_with_owner_and_separate_job_title(owner, db):
    m = owner.me["memberships"][0]
    assert m["role"] == "owner"
    assert m["job_title"] == "CEO"
    assert "approval.decide" in m["permissions"] and "org.delete" in m["permissions"]
    row = db.scalar(select(OrganizationMembership).where(OrganizationMembership.user_id == owner.user_id))
    assert (row.role, row.job_title) == ("owner", "CEO")
    # A company profile exists from the start, named after the workspace.
    r = owner.get("/api/v1/company/profile")
    assert r.status_code == 200 and r.json()["company_name"] == "Acme Trading"


def test_job_title_is_optional_and_grants_nothing(client):
    r = client.post("/api/v1/auth/register", json={"email": "solo@example.com", "password": PASSWORD,
                                                   "full_name": "Solo", "organization_name": "Solo Ltd"})
    assert r.status_code == 201
    assert r.json()["memberships"][0] == {**r.json()["memberships"][0], "role": "owner", "job_title": None}


def test_duplicate_email_rejected(owner, client):
    r = client.post("/api/v1/auth/register", json={"email": "CEO@acme.example.com", "password": PASSWORD,
                                                   "full_name": "X", "organization_name": "Y"})
    assert r.status_code == 409


def test_weak_password_and_bad_email_rejected(client):
    r = client.post("/api/v1/auth/register", json={"email": "nope", "password": "short", "full_name": "X",
                                                   "organization_name": "Y"})
    assert r.status_code == 422
    fields = {d["loc"][-1] for d in r.json()["error"]["details"]}
    assert {"email", "password"} <= fields


def test_login_logout_and_me(owner):
    c = new_client()
    assert c.get("/api/v1/auth/me").status_code == 401
    r = c.post("/api/v1/auth/login", json={"email": owner.email, "password": PASSWORD})
    assert r.status_code == 200 and r.json()["user"]["email"] == owner.email
    assert c.get("/api/v1/auth/me").status_code == 200
    assert c.post("/api/v1/auth/logout").status_code == 204
    assert c.get("/api/v1/auth/me").status_code == 401


def test_wrong_password_is_generic_and_locks_after_limit(owner, monkeypatch):
    from abos.core.config import get_settings

    monkeypatch.setattr(get_settings(), "login_failure_limit", 3)
    c = new_client()
    for _ in range(3):
        r = c.post("/api/v1/auth/login", json={"email": owner.email, "password": "wrong-password-123"})
        assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_credentials"
    r = c.post("/api/v1/auth/login", json={"email": owner.email, "password": PASSWORD})
    assert r.status_code == 429 and r.headers["Retry-After"]
    # Unknown accounts get the same answer as wrong passwords.
    r = c.post("/api/v1/auth/login", json={"email": "ghost@example.com", "password": "whatever-123"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_credentials"


def test_csrf_header_required_for_unsafe_methods(owner):
    from fastapi.testclient import TestClient

    from abos.main import app

    bare = TestClient(app)
    r = bare.post("/api/v1/auth/login", json={"email": owner.email, "password": PASSWORD})
    assert r.status_code == 403 and r.json()["error"]["code"] == "csrf_failed"


def test_email_verification(owner):
    token = last_email_token(owner.email, "/verify-email")
    r = owner.client.post("/api/v1/auth/verify-email", json={"token": token})
    assert r.status_code == 200 and r.json()["email_verified_at"]
    # Single use.
    assert owner.client.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 400


def test_password_reset_flow_revokes_sessions(owner, db):
    c = new_client()
    assert c.post("/api/v1/auth/password-reset/request", json={"email": owner.email}).status_code == 202
    # Unknown emails look identical and send nothing.
    assert c.post("/api/v1/auth/password-reset/request", json={"email": "ghost@example.com"}).status_code == 202
    assert db.scalar(select(EmailOutbox).where(EmailOutbox.to_email == "ghost@example.com")) is None
    token = last_email_token(owner.email, "/reset-password")
    r = c.post("/api/v1/auth/password-reset/confirm", json={"token": token, "new_password": "a-brand-new-pass"})
    assert r.status_code == 204
    assert owner.get("/api/v1/auth/me", org=False).status_code == 401  # old session revoked
    assert c.post("/api/v1/auth/login", json={"email": owner.email, "password": "a-brand-new-pass"}).status_code == 200


def test_change_password_keeps_current_session_only(owner):
    other = new_client()
    other.post("/api/v1/auth/login", json={"email": owner.email, "password": PASSWORD})
    r = owner.client.post("/api/v1/auth/password", json={"current_password": "nope-nope-nope",
                                                         "new_password": "another-good-pass"})
    assert r.status_code == 400
    r = owner.client.post("/api/v1/auth/password", json={"current_password": PASSWORD,
                                                         "new_password": "another-good-pass"})
    assert r.status_code == 204
    assert owner.client.get("/api/v1/auth/me").status_code == 200
    assert other.get("/api/v1/auth/me").status_code == 401


def test_sessions_list_and_revoke(owner):
    other = new_client()
    other.post("/api/v1/auth/login", json={"email": owner.email, "password": PASSWORD})
    sessions = owner.client.get("/api/v1/auth/sessions").json()
    assert len(sessions) == 2 and sum(s["current"] for s in sessions) == 1
    victim = next(s for s in sessions if not s["current"])
    assert owner.client.delete(f"/api/v1/auth/sessions/{victim['id']}").status_code == 204
    assert other.get("/api/v1/auth/me").status_code == 401


def test_create_additional_workspace(owner):
    r = owner.post("/api/v1/orgs", json={"name": "Acme Logistics", "job_title": "Founder"}, org=False)
    assert r.status_code == 201
    new_id = r.json()["id"]
    me = owner.client.get("/api/v1/auth/me").json()
    assert {m["organization"]["id"]: m["role"] for m in me["memberships"]}[new_id] == "owner"
    assert owner.client.get("/api/v1/company/profile", headers={"X-Org-Id": new_id}).json()["company_name"] \
        == "Acme Logistics"


def test_security_headers(client):
    r = client.get("/api/health")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
    assert r.headers["X-Request-Id"]


def test_register_twice_same_org_name_gets_unique_slug():
    a = register("a@example.com", org="Same Name")
    b = register("b@example.com", org="Same Name")
    assert a.me["memberships"][0]["organization"]["slug"] != b.me["memberships"][0]["organization"]["slug"]
