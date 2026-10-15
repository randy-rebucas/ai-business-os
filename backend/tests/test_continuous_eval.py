"""SPEC §4 continuous evaluation: after a material change the affected agents are identified, and they can't be
resumed until they pass a regression run. Material changes: confirmed rules change, a new configuration version."""

from tests.test_agents_api import draft_body, setup_company
from tests.test_execution import active
from tests.test_simulation import run


def _retest(actor) -> dict[str, list[str]]:
    return {x["agent"]: x["reasons"] for x in actor.get("/api/v1/dashboard").json()["needs_retest"]}


def test_material_changes_flag_affected_agents_until_regression_tested(owner):
    setup_company(owner)
    inst, cfg = active(owner)
    name = inst["name"]
    assert _retest(owner) == {}
    body = {"config_hash": cfg["config_hash"]}

    # 1. A confirmed rule that applies to Finance changes the policy version → Finance is flagged.
    r = owner.post("/api/v1/rules", json={"title": "Reminder cap", "statement": "Send at most one reminder a week.",
                                          "applies_to": ["finance"]})
    assert r.status_code == 201, r.text
    reasons = _retest(owner)[name]
    assert any("business-rule change" in x for x in reasons), reasons
    assert owner.post(f"/api/v1/agents/{inst['id']}/pause", json={}).status_code == 200
    blocked = owner.post(f"/api/v1/agents/{inst['id']}/resume", json=body)
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "not_ready"
    run(owner, inst)  # regression run on the unchanged configuration
    assert _retest(owner) == {}
    assert owner.post(f"/api/v1/agents/{inst['id']}/resume", json=body).json()["status"] == "active"

    # 2. Editing the configuration of an active agent takes it out of service: it goes back through approval and
    # testing (lifecycle), so it can't run on an untested change; the readiness gate shows why.
    current = owner.get(f"/api/v1/agents/{inst['id']}").json()["current_config"]
    edited = draft_body(current)
    edited["config"]["limits"]["monthly_budget_usd"] = 45
    assert owner.put(f"/api/v1/agents/{inst['id']}/config/draft", json=edited).status_code == 200
    assert owner.get(f"/api/v1/agents/{inst['id']}").json()["status"] == "configuring"
    gate = owner.get(f"/api/v1/agents/{inst['id']}/readiness").json()
    assert not gate["ready"] and {i["key"] for i in gate["items"] if not i["ok"]} >= {"approved", "tested"}
    r = owner.post("/api/v1/workflows", json={"agent_id": inst["id"], "task_key": "review-outstanding-invoices"})
    assert r.status_code == 409, r.text
    # The list is scoped like the rest of the Control Center.
    assert owner.get("/api/v1/dashboard?department=Sales").json()["needs_retest"] == []
