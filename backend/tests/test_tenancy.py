"""Organization isolation and role-based authorization at the API layer (SPEC §3 acceptance, §6)."""

import uuid

from tests.conftest import join


def test_non_member_cannot_use_another_orgs_id(owner, rival):
    for path in ("/api/v1/org", "/api/v1/company/profile", "/api/v1/company/departments", "/api/v1/audit"):
        r = rival.client.get(path, headers={"X-Org-Id": owner.org_id})
        assert r.status_code == 403, path
    # Unknown org ids look exactly like foreign ones (no probing).
    r = rival.client.get("/api/v1/org", headers={"X-Org-Id": str(uuid.uuid4())})
    assert r.status_code == 403
    assert rival.client.get("/api/v1/org").status_code == 400  # header required


def test_records_of_another_org_are_not_found_by_id(owner, rival):
    dept = owner.post("/api/v1/company/departments", json={"name": "Finance"}).json()
    r = rival.patch(f"/api/v1/company/departments/{dept['id']}", json={"name": "Pwned"})
    assert r.status_code == 404
    assert rival.delete(f"/api/v1/company/departments/{dept['id']}").status_code == 404
    assert rival.get("/api/v1/company/departments").json() == []
    assert owner.get("/api/v1/company/departments").json()[0]["name"] == "Finance"


def test_cannot_reference_another_orgs_department(owner, rival):
    foreign = owner.post("/api/v1/company/departments", json={"name": "Finance"}).json()
    r = rival.post("/api/v1/company/job-roles", json={"title": "Accountant", "department_id": foreign["id"]})
    assert r.status_code == 422
    assert r.json()["error"]["details"][0]["loc"][-1] == "department_id"


def test_rival_edits_do_not_touch_owner_profile(owner, rival):
    rival.patch("/api/v1/company/profile", json={"industry": "Shipping"})
    assert owner.get("/api/v1/company/profile").json()["industry"] is None


def test_viewer_can_read_but_not_write(owner):
    viewer = join(owner, "viewer@acme.example.com", "viewer")
    assert viewer.get("/api/v1/company/profile").status_code == 200
    assert viewer.patch("/api/v1/company/profile", json={"industry": "Retail"}).status_code == 403
    assert viewer.post("/api/v1/company/departments", json={"name": "Ops"}).status_code == 403
    assert viewer.get("/api/v1/audit").status_code == 403


def test_manager_edits_company_but_cannot_manage_members(owner):
    manager = join(owner, "manager@acme.example.com", "manager")
    assert manager.patch("/api/v1/company/profile", json={"industry": "Retail"}).status_code == 200
    r = manager.post("/api/v1/org/members", json={"email": "x@example.com", "role": "viewer"})
    assert r.status_code == 403
    assert manager.patch("/api/v1/org", json={"name": "Renamed"}).status_code == 403


def test_member_management_rules(owner):
    admin = join(owner, "admin@acme.example.com", "admin")
    member = join(owner, "member@acme.example.com", "member")
    # Admins manage members but cannot mint owners.
    r = admin.patch(f"/api/v1/org/members/{member.user_id}", json={"role": "owner"})
    assert r.status_code == 403
    r = admin.patch(f"/api/v1/org/members/{member.user_id}", json={"role": "manager", "job_title": "Ops Lead"})
    assert r.status_code == 200 and (r.json()["role"], r.json()["job_title"]) == ("manager", "Ops Lead")
    # The last owner can't be demoted or removed.
    r = owner.patch(f"/api/v1/org/members/{owner.user_id}", json={"role": "admin"})
    assert r.status_code == 409
    assert owner.delete(f"/api/v1/org/members/{owner.user_id}").status_code == 409
    # Removing a member cuts their access immediately.
    assert owner.delete(f"/api/v1/org/members/{member.user_id}").status_code == 204
    assert member.get("/api/v1/company/profile").status_code == 403


def test_add_member_requires_registered_user_and_no_duplicates(owner):
    r = owner.post("/api/v1/org/members", json={"email": "nobody@example.com", "role": "member"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "user_not_found"
    join(owner, "dup@acme.example.com", "member")
    r = owner.post("/api/v1/org/members", json={"email": "dup@acme.example.com", "role": "member"})
    assert r.status_code == 409


def test_members_list_shows_titles(owner):
    join(owner, "cfo@acme.example.com", "admin", name="Cora")
    owner.patch(f"/api/v1/org/members/{owner.user_id}", json={"job_title": "Chief Executive"})
    members = {m["email"]: m for m in owner.get("/api/v1/org/members").json()}
    assert members[owner.email]["job_title"] == "Chief Executive"
    assert members["cfo@acme.example.com"]["role"] == "admin"
