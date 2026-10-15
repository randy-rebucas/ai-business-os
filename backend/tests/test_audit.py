import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from abos.audit.models import AuditEvent
from tests.conftest import join


def test_org_creation_and_changes_are_audited(owner):
    owner.patch("/api/v1/company/profile", json={"industry": "Retail"})
    events = owner.get("/api/v1/audit").json()
    actions = [e["action"] for e in events]
    assert "org.created" in actions and "company.profile_updated" in actions
    upd = next(e for e in events if e["action"] == "company.profile_updated")
    assert upd["data"] == {"fields": ["industry"]} and upd["actor_name"] == "Test User"
    # A no-op update records nothing.
    owner.patch("/api/v1/company/profile", json={"industry": "Retail"})
    assert len(owner.get("/api/v1/audit?action=company.profile_updated").json()) == 1


def test_audit_requires_permission_and_is_org_scoped(owner, rival):
    member = join(owner, "member@acme.example.com", "member")
    assert member.get("/api/v1/audit").status_code == 403
    assert all(e["action"] != "org.created" or e["data"]["name"] == "Rival Corp"
               for e in rival.get("/api/v1/audit").json())


def test_audit_events_are_append_only_in_the_database(owner, db):
    event = db.scalar(select(AuditEvent).limit(1))
    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(text("UPDATE audit_events SET action = 'tampered' WHERE id = :id"), {"id": event.id})
    db.rollback()
    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(text("DELETE FROM audit_events WHERE id = :id"), {"id": event.id})
    db.rollback()


def test_app_role_has_no_update_or_delete_privilege_on_audit(app_db):
    rows = app_db.execute(text("SELECT privilege_type FROM information_schema.role_table_grants "
                               "WHERE grantee = 'abos_app' AND table_name = 'audit_events'")).scalars().all()
    assert set(rows) >= {"SELECT", "INSERT"} and not ({"UPDATE", "DELETE"} & set(rows))
