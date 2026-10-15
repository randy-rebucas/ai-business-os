"""Company profile and onboarding data (SPEC §3 step 1)."""

from tests.conftest import new_client


def _section(completeness: dict, key: str) -> dict:
    return next(s for s in completeness["sections"] if s["key"] == key)


def test_profile_patch_persists_across_sessions(owner):
    body = {
        "legal_name": "Acme Trading Inc.", "trading_name": "Acme", "industry": "Wholesale",
        "business_category": "B2B distribution", "description": "We distribute office supplies.",
        "target_customers": "SMEs in Metro Manila", "company_size": "11-50", "employee_count": 34,
        "timezone": "Asia/Manila",
        "operating_schedule": {"mon": {"open": "08:00", "close": "17:00"}, "sat": None},
        "holidays": [{"date": "2026-12-25", "name": "Christmas"}],
        "reporting_cadence": "daily", "notification_channels": {"in_app": True, "email": True, "sms": False},
        "monthly_ai_budget": "250.00", "budget_currency": "PHP",
    }
    r = owner.patch("/api/v1/company/profile", json=body)
    assert r.status_code == 200, r.text
    # A fresh login (new session) sees the same data.
    c = new_client()
    c.post("/api/v1/auth/login", json={"email": owner.email, "password": "correct-horse-battery"})
    p = c.get("/api/v1/company/profile", headers={"X-Org-Id": owner.org_id}).json()
    assert p["legal_name"] == "Acme Trading Inc." and p["timezone"] == "Asia/Manila"
    assert p["operating_schedule"]["mon"] == {"open": "08:00", "close": "17:00"} and p["operating_schedule"]["sat"] is None
    assert p["holidays"] == [{"date": "2026-12-25", "name": "Christmas"}]
    assert p["monthly_ai_budget"] == "250.00" and p["budget_currency"] == "PHP"


def test_partial_update_leaves_other_fields_and_null_clears(owner):
    owner.patch("/api/v1/company/profile", json={"industry": "Retail", "description": "Shops"})
    owner.patch("/api/v1/company/profile", json={"description": None})
    p = owner.get("/api/v1/company/profile").json()
    assert (p["industry"], p["description"]) == ("Retail", None)
    r = owner.patch("/api/v1/company/profile", json={"company_name": None})
    assert r.status_code == 422


def test_profile_validation(owner):
    cases = [
        {"timezone": "Mars/Olympus"},
        {"operating_schedule": {"mon": {"open": "18:00", "close": "09:00"}}},
        {"operating_schedule": {"funday": {"open": "09:00", "close": "10:00"}}},
        {"company_size": "huge"},
        {"monthly_ai_budget": "-5"},
        {"budget_currency": "pesos"},
        {"skipped_sections": ["not-a-section"]},
    ]
    for body in cases:
        r = owner.patch("/api/v1/company/profile", json=body)
        assert r.status_code == 422, body


def test_completeness_tracks_missing_and_skipped_sections(owner):
    c = owner.get("/api/v1/company/completeness").json()
    assert c["percent"] == 0 and all(s["status"] == "missing" for s in c["sections"])
    owner.patch("/api/v1/company/profile", json={"industry": "Retail"})
    owner.patch("/api/v1/company/profile", json={"skipped_sections": ["software"]})
    owner.post("/api/v1/company/offerings", json={"name": "Printer paper", "kind": "product"})
    c = owner.get("/api/v1/company/completeness").json()
    assert _section(c, "basics")["status"] == "partial"
    assert "Company description" in _section(c, "basics")["missing"]
    assert _section(c, "software")["status"] == "skipped"
    assert _section(c, "offerings")["status"] == "complete"
    assert c["percent"] == round(100 / 13)


def test_collection_crud_and_audit(owner):
    dept = owner.post("/api/v1/company/departments", json={"name": "Finance", "head_name": "Cora"}).json()
    role = owner.post("/api/v1/company/job-roles", json={"title": "Accountant", "department_id": dept["id"],
                                                          "headcount": 2}).json()
    assert role["department_id"] == dept["id"]
    r = owner.patch(f"/api/v1/company/job-roles/{role['id']}", json={"headcount": 3})
    assert r.status_code == 200 and r.json()["headcount"] == 3 and r.json()["title"] == "Accountant"
    # PATCH re-validates the merged record: required fields can't be nulled.
    assert owner.patch(f"/api/v1/company/job-roles/{role['id']}", json={"title": None}).status_code == 422
    # Deleting a department detaches roles instead of deleting them.
    assert owner.delete(f"/api/v1/company/departments/{dept['id']}").status_code == 204
    assert owner.get("/api/v1/company/job-roles").json()[0]["department_id"] is None
    actions = [e["action"] for e in owner.get("/api/v1/audit?action=company.").json()]
    assert {"company.departments.created", "company.job-roles.updated", "company.departments.deleted"} <= set(actions)


def test_duplicate_department_name_conflicts(owner):
    owner.post("/api/v1/company/departments", json={"name": "Sales"})
    assert owner.post("/api/v1/company/departments", json={"name": "Sales"}).status_code == 409


def test_only_one_primary_location(owner):
    a = owner.post("/api/v1/company/locations", json={"name": "HQ", "kind": "headquarters", "is_primary": True}).json()
    owner.post("/api/v1/company/locations", json={"name": "Cebu branch", "kind": "branch", "is_primary": True,
                                                  "timezone": "Asia/Manila"})
    locs = {loc["name"]: loc for loc in owner.get("/api/v1/company/locations").json()}
    assert locs["Cebu branch"]["is_primary"] and not locs["HQ"]["is_primary"]
    assert owner.patch(f"/api/v1/company/locations/{a['id']}", json={"timezone": "Nope/Nope"}).status_code == 422


def test_all_collections_round_trip(owner):
    bodies = {
        "objectives": {"title": "Grow revenue", "kpi_name": "Monthly revenue", "kpi_target": "1500000",
                       "kpi_unit": "PHP", "target_date": "2027-06-30"},
        "processes": {"name": "Purchase approval", "approval_procedure": "Above 50k needs CEO sign-off"},
        "software": {"name": "QuickBooks", "category": "accounting", "integration_wanted": True},
        "challenges": {"title": "Late invoice follow-ups", "severity": "high"},
        "offerings": {"name": "Delivery", "kind": "service", "pricing_note": "Free above 5k"},
    }
    for key, body in bodies.items():
        r = owner.post(f"/api/v1/company/{key}", json=body)
        assert r.status_code == 201, (key, r.text)
        assert len(owner.get(f"/api/v1/company/{key}").json()) == 1


def test_onboarding_complete_is_idempotent(owner):
    first = owner.post("/api/v1/company/onboarding/complete").json()["onboarding_completed_at"]
    assert first
    assert owner.post("/api/v1/company/onboarding/complete").json()["onboarding_completed_at"] == first


def test_timezones_endpoint(owner):
    zones = owner.get("/api/v1/company/timezones", org=False).json()
    assert "Asia/Manila" in zones and "UTC" in zones
