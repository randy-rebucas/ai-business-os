"""Row-level security is the second tenancy layer (ADR-003): a query that forgets its organization filter must still
see, change or create nothing outside the active org."""

import uuid

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import ProgrammingError

from abos.company.models import Department
from abos.core.db import Base
from abos.core.tenancy import set_tenant, system_scope


@pytest.fixture
def two_orgs(owner, rival):
    a = owner.post("/api/v1/company/departments", json={"name": "Finance"}).json()
    b = rival.post("/api/v1/company/departments", json={"name": "Rival Finance"}).json()
    return owner, rival, a, b


def test_every_tenant_table_has_row_level_security(db):
    tenant_tables = {t.name for t in Base.metadata.sorted_tables
                     if "organization_id" in t.c and t.name != "organization_memberships"}
    rows = db.execute(text("""
        SELECT c.relname, c.relrowsecurity, count(p.polname) AS policies
        FROM pg_class c LEFT JOIN pg_policy p ON p.polrelid = c.oid
        WHERE c.relname = ANY(:names) GROUP BY c.relname, c.relrowsecurity"""), {"names": list(tenant_tables)}).all()
    status = {r.relname: (r.relrowsecurity, r.policies) for r in rows}
    missing = sorted(t for t in tenant_tables if status.get(t) != (True, 1))
    assert not missing, f"tenant tables without RLS + policy: {missing}"
    assert {"audit_events", "company_profiles", "departments"} <= tenant_tables


def test_app_role_cannot_bypass_rls(app_db):
    row = app_db.execute(text("SELECT current_user AS u, rolsuper, rolbypassrls FROM pg_roles "
                              "WHERE rolname = current_user")).one()
    assert row.u == "abos_app" and not row.rolsuper and not row.rolbypassrls


def test_unfiltered_query_sees_only_the_bound_tenant(two_orgs, app_db):
    owner, rival, a, b = two_orgs
    assert app_db.scalars(select(Department)).all() == []  # no tenant bound → nothing
    set_tenant(app_db, uuid.UUID(owner.org_id))
    assert [str(d.id) for d in app_db.scalars(select(Department))] == [a["id"]]
    assert app_db.get(Department, uuid.UUID(b["id"])) is None
    res = app_db.execute(update(Department).where(Department.id == uuid.UUID(b["id"])).values(name="pwned"))
    assert res.rowcount == 0  # writes to the other tenant's rows silently match nothing
    app_db.commit()
    assert len(app_db.scalars(select(Department)).all()) == 1  # binding survives commits
    with system_scope(app_db):
        assert len(app_db.scalars(select(Department)).all()) == 2
    assert len(app_db.scalars(select(Department)).all()) == 1


def test_cannot_insert_rows_for_another_tenant(two_orgs, app_db):
    owner, rival, a, b = two_orgs
    set_tenant(app_db, uuid.UUID(owner.org_id))
    with pytest.raises(ProgrammingError, match="row-level security"):
        app_db.execute(text("""INSERT INTO departments (id, organization_id, name, created_at, updated_at)
                               VALUES (gen_random_uuid(), :org, 'Injected', now(), now())"""), {"org": rival.org_id})
    app_db.rollback()


def test_api_stays_isolated_even_if_service_forgets_the_org_filter(two_orgs, monkeypatch):
    """Simulate a bug: the list query drops its organization filter. RLS must still hide the rival's rows."""
    owner, rival, a, b = two_orgs
    from abos.company import service

    def buggy_list(db, org_id, c):
        return list(db.scalars(select(c.model)))

    monkeypatch.setattr(service, "list_items", buggy_list)
    names = [d["name"] for d in owner.get("/api/v1/company/departments").json()]
    assert names == ["Finance"]
