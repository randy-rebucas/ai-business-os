"""Phase 3 integration: catalog → recommendation → hire → generate → edit → submit → CEO approval, with the
approval bound to the configuration hash, the execution guard, role checks and tenant isolation."""

import uuid

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import ProgrammingError

from abos.agents import service as agent_service
from abos.agents.models import AgentConfiguration, AgentInstance, TaskDefinition
from abos.audit.models import AuditEvent
from abos.core.tenancy import set_tenant
from abos.governance.models import Approval
from abos.llm import gateway
from tests.conftest import join

HOURS = {d: {"open": "09:00", "close": "17:00"} for d in ("mon", "tue", "wed", "thu", "fri")}


def setup_company(actor, budget="300.00", currency="USD"):
    r = actor.patch("/api/v1/company/profile", json={
        "timezone": "Asia/Manila", "operating_schedule": HOURS, "monthly_ai_budget": budget,
        "budget_currency": currency, "reporting_cadence": "daily", "company_size": "11-50",
        "holidays": [{"date": "2026-12-25", "name": "Christmas"}]})
    assert r.status_code == 200, r.text
    for path, body in (("departments", {"name": "Finance"}),
                       ("software", {"name": "Xero", "category": "accounting"}),
                       ("challenges", {"title": "Late customer invoices", "severity": "high",
                                       "description": "Receivables slip past 60 days"}),
                       ("objectives", {"title": "Improve cash flow", "kpi_name": "Days sales outstanding"})):
        assert actor.post(f"/api/v1/company/{path}", json=body).status_code == 201


def hire(actor, key="finance"):
    r = actor.post("/api/v1/agents", json={"definition_keys": [key]})
    assert r.status_code == 201, r.text
    return r.json()[0]


def generated(actor, key="finance"):
    inst = hire(actor, key)
    r = actor.post(f"/api/v1/agents/{inst['id']}/config/generate")
    assert r.status_code == 200, r.text
    return inst, r.json()


def draft_body(cfg):
    tasks = []
    for t in cfg["tasks"]:
        tasks.append({k: t[k] for k in ("key", "title", "description", "inputs", "actions", "expected_output",
                                        "completion_criteria", "priority", "sla_minutes", "policy_refs",
                                        "required_permissions", "approval_required", "approval_reason", "failure",
                                        "depends_on")}
                     | {"trigger": {"type": t["trigger_type"], "schedule": t["schedule"], "event": t["event"]}})
    return {"config": cfg["config"], "tasks": tasks}


def submitted(actor, key="finance"):
    inst, cfg = generated(actor, key)
    r = actor.post(f"/api/v1/agents/{inst['id']}/config/submit")
    assert r.status_code == 200, r.text
    return inst, r.json()


def decide(actor, cfg, decision="approved", note=None, config_hash=None):
    return actor.post(f"/api/v1/approvals/configurations/{cfg['id']}/decide",
                      json={"decision": decision, "note": note, "config_hash": config_hash or cfg["config_hash"]})


# ---- catalog & recommendation ----------------------------------------------------------------------------------

def test_catalog_lists_eight_versioned_definitions_from_the_database(owner, db):
    r = owner.get("/api/v1/agents/catalog")
    assert r.status_code == 200
    items = r.json()
    assert [d["letter"] for d in items] == list("ABCDEFGH")
    assert all(d["status"] == "available" and d["version"] == 1 for d in items)
    finance = next(d for d in items if d["key"] == "finance")
    assert "Issuing payments or transfers" in finance["prohibited"]
    assert finance["permission_ceilings"]["finance.execute"] == "denied"
    assert owner.get("/api/v1/agents/catalog/finance").json()["name"] == "Finance and Accounting Agent"
    assert owner.get("/api/v1/agents/catalog/nope").status_code == 404
    vocab = owner.get("/api/v1/agents/policy").json()
    assert {s["key"] for s in vocab["scopes"]} >= {"data.read", "finance.execute"}


def test_app_role_cannot_change_the_catalog(app_db):
    with pytest.raises(ProgrammingError, match="permission denied"):
        app_db.execute(text("UPDATE agent_definitions SET name = 'pwned'"))
    app_db.rollback()


def test_recommendation_is_rule_based_and_explained(owner):
    empty = owner.get("/api/v1/agents/recommendation").json()
    assert empty["recommended_keys"] == []
    assert "software you use" in empty["profile_gaps"]
    setup_company(owner)
    rec = owner.get("/api/v1/agents/recommendation").json()
    assert rec["recommended_keys"][0] == "finance"
    finance = next(i for i in rec["items"] if i["key"] == "finance")
    assert "Software: Xero (accounting)" in finance["reasons"]
    assert "Challenge: Late customer invoices (high)" in finance["reasons"]
    assert rec["budget"]["status"] == "within"
    assert rec == owner.get("/api/v1/agents/recommendation").json()  # deterministic


def test_recommendation_respects_a_usd_budget_and_refuses_to_convert_currencies(owner):
    setup_company(owner, budget="70.00")
    owner.post("/api/v1/company/departments", json={"name": "Customer service"})
    owner.post("/api/v1/company/software", json={"name": "Zendesk", "category": "support"})
    rec = owner.get("/api/v1/agents/recommendation").json()
    assert float(rec["total_estimated_monthly_usd"]) <= 70
    assert any(i["excluded_reason"] for i in rec["items"])
    owner.patch("/api/v1/company/profile", json={"budget_currency": "PHP"})
    rec = owner.get("/api/v1/agents/recommendation").json()
    assert rec["budget"]["status"] == "not_comparable"


# ---- hiring ----------------------------------------------------------------------------------------------------

def test_hire_permissions_duplicates_and_rehire(owner):
    manager = join(owner, "manager@acme.example.com", "manager")
    assert manager.post("/api/v1/agents", json={"definition_keys": ["finance"]}).status_code == 403
    inst = hire(owner)
    assert inst["status"] == "selected"
    assert owner.post("/api/v1/agents", json={"definition_keys": ["finance"]}).status_code == 409
    assert owner.post("/api/v1/agents", json={"definition_keys": ["ghost"]}).status_code == 404
    catalog = {d["key"]: d for d in owner.get("/api/v1/agents/catalog").json()}
    assert catalog["finance"]["status"] == "selected" and catalog["finance"]["instance_id"] == inst["id"]
    r = owner.post(f"/api/v1/agents/{inst['id']}/retire", json={"reason": "Not needed yet"})
    assert r.json()["status"] == "retired"
    assert owner.post(f"/api/v1/agents/{inst['id']}/config/generate").status_code == 409
    assert hire(owner)["id"] != inst["id"]  # a retired agent can be hired again
    team = owner.post("/api/v1/agents", json={"definition_keys": ["sales", "support"], "source": "recommended"})
    assert team.status_code == 201 and len(team.json()) == 2
    names = [a["definition_key"] for a in owner.get("/api/v1/agents").json()]
    assert names == ["sales", "finance", "support"]


# ---- configuration -------------------------------------------------------------------------------------------

def test_generate_is_labelled_template_with_evidence_and_valid_for_a_set_up_company(owner):
    setup_company(owner)
    inst, cfg = generated(owner)
    assert cfg["version"] == 1 and cfg["status"] == "draft" and cfg["source"] == "generated"
    assert cfg["generation"]["is_dev"] is True
    assert "Development adapter" in cfg["generation"]["label"]
    assert [i for i in cfg["issues"] if i["severity"] == "error"] == []
    assert {t["key"] for t in cfg["tasks"]} == {"review-outstanding-invoices", "expense-categorisation",
                                                 "monthly-summary"}
    monthly = next(t for t in cfg["tasks"] if t["key"] == "monthly-summary")
    assert monthly["depends_on"] == ["review-outstanding-invoices"]
    assert cfg["config"]["permissions"]["finance.execute"] == "denied"
    detail = owner.get(f"/api/v1/agents/{inst['id']}").json()
    assert detail["status"] == "configuring"
    assert detail["execution"] == {"allowed": False, "reason": "Agent is configuring, not active"}


def test_incomplete_profile_blocks_submission_with_reasons(owner):
    inst, cfg = generated(owner)  # no time zone or hours set
    errors = [i["message"] for i in cfg["issues"] if i["severity"] == "error"]
    assert any("time zone" in m for m in errors)
    r = owner.post(f"/api/v1/agents/{inst['id']}/config/submit")
    assert r.status_code == 409 and r.json()["error"]["code"] == "config_invalid"
    assert owner.get(f"/api/v1/agents/{inst['id']}").json()["status"] == "configuring"


def test_edit_draft_in_place_and_reject_bad_input(owner):
    setup_company(owner)
    inst, cfg = generated(owner)
    body = draft_body(cfg)
    body["config"]["limits"]["monthly_budget_usd"] = "45.00"
    body["config"]["job"]["mission"] = "Keep receivables under control for Acme."
    r = owner.put(f"/api/v1/agents/{inst['id']}/config/draft", json=body)
    assert r.status_code == 200, r.text
    edited = r.json()
    assert edited["version"] == 1 and edited["source"] == "edited" and edited["config_hash"] != cfg["config_hash"]
    assert edited["config"]["job"]["mission"] == "Keep receivables under control for Acme."
    # Structural errors are 422 and change nothing.
    bad = draft_body(edited)
    bad["tasks"][0]["key"] = "Not A Key"
    assert owner.put(f"/api/v1/agents/{inst['id']}/config/draft", json=bad).status_code == 422
    # Security boundaries are errors that block submission.
    over = draft_body(edited)
    over["config"]["permissions"]["finance.execute"] = "approval_required"
    saved = owner.put(f"/api/v1/agents/{inst['id']}/config/draft", json=over).json()
    assert any(i["field"] == "permissions.finance.execute" for i in saved["issues"])
    r = owner.post(f"/api/v1/agents/{inst['id']}/config/submit")
    assert r.status_code == 409
    assert any(d["field"] == "permissions.finance.execute" for d in r.json()["error"]["details"])


def test_approval_is_bound_to_the_reviewed_hash_and_recorded(owner, db):
    setup_company(owner)
    inst, cfg = submitted(owner)
    assert owner.get(f"/api/v1/agents/{inst['id']}").json()["status"] == "awaiting_approval"
    pending = owner.get("/api/v1/approvals/pending").json()
    assert [p["config_id"] for p in pending] == [cfg["id"]]
    manager = join(owner, "manager@acme.example.com", "manager")
    assert decide(manager, cfg).status_code == 403  # approval.decide is owner-only
    r = decide(owner, cfg, config_hash="0" * 64)
    assert r.status_code == 409 and r.json()["error"]["code"] == "config_changed"
    r = decide(owner, cfg)
    assert r.status_code == 200, r.text
    a = r.json()
    assert a["decision"] == "approved" and a["decided_by_id"] == owner.user_id and a["decided_by_role"] == "owner"
    assert a["subject_hash"] == cfg["config_hash"] and a["subject_version"] == 1
    assert a["policy_version"].startswith("platform-2026.10/rules-0-")
    # Finance starts observe-only: it reads and drafts, nothing else (writes stay denied until the CEO raises it).
    assert a["scope"]["permissions"] == {"data.read": "auto", "records.draft": "auto"}
    assert a["scope"]["automation_level"] == "observe" and "reminder.send" not in a["scope"]["tools"]
    assert {t["key"] for t in a["scope"]["tasks"]} == {t["key"] for t in cfg["tasks"]}
    detail = owner.get(f"/api/v1/agents/{inst['id']}").json()
    assert detail["status"] == "testing" and detail["approved_config_id"] == cfg["id"]
    assert detail["current_config"]["status"] == "approved"
    assert detail["execution"]["allowed"] is False  # approved ≠ active: Phase 4 readiness comes first
    assert decide(owner, cfg).status_code == 409  # not pending any more
    actions = set(db.scalars(select(AuditEvent.action).where(AuditEvent.organization_id == uuid.UUID(owner.org_id))))
    assert {"agents.hired", "agents.config_generated", "agents.config_submitted", "approvals.approved"} <= actions


def test_approvals_are_insert_only_for_the_app_role(owner, app_db):
    setup_company(owner)
    _, cfg = submitted(owner)
    decide(owner, cfg)
    set_tenant(app_db, uuid.UUID(owner.org_id))
    with pytest.raises(ProgrammingError, match="permission denied"):
        app_db.execute(update(Approval).values(decision="rejected"))
    app_db.rollback()


def test_editing_after_approval_needs_a_new_approval(owner):
    setup_company(owner)
    inst, cfg = submitted(owner)
    decide(owner, cfg)
    body = draft_body(owner.get(f"/api/v1/agents/{inst['id']}").json()["current_config"])
    body["config"]["limits"]["max_runs_per_day"] = 10
    v2 = owner.put(f"/api/v1/agents/{inst['id']}/config/draft", json=body).json()
    assert v2["version"] == 2 and v2["status"] == "draft"
    detail = owner.get(f"/api/v1/agents/{inst['id']}").json()
    assert detail["status"] == "configuring" and detail["approved_config_id"] == cfg["id"]
    versions = owner.get(f"/api/v1/agents/{inst['id']}/config/versions").json()
    assert [(v["version"], v["status"]) for v in versions] == [(2, "draft"), (1, "approved")]
    old = owner.get(f"/api/v1/agents/{inst['id']}/config/versions/1").json()
    assert old["config_hash"] == cfg["config_hash"]


def test_reject_requires_a_note_and_returns_to_configuring(owner):
    setup_company(owner)
    inst, cfg = submitted(owner)
    assert decide(owner, cfg, "rejected").status_code == 422
    r = decide(owner, cfg, "rejected", note="Lower the budget to $40")
    assert r.status_code == 200 and r.json()["decision"] == "rejected"
    detail = owner.get(f"/api/v1/agents/{inst['id']}").json()
    assert detail["status"] == "configuring" and detail["status_reason"] == "Changes requested: Lower the budget to $40"
    assert detail["current_config"]["status"] == "rejected"
    regenerated = owner.post(f"/api/v1/agents/{inst['id']}/config/generate").json()
    assert regenerated["version"] == 2


def test_a_resubmission_withdraws_the_pending_version(owner):
    setup_company(owner)
    inst, cfg = submitted(owner)
    owner.post(f"/api/v1/agents/{inst['id']}/config/generate")  # changed while waiting for the CEO
    assert owner.get("/api/v1/approvals/pending").json() == []
    r = decide(owner, cfg)
    assert r.status_code == 409 and r.json()["error"]["code"] == "not_pending"
    versions = owner.get(f"/api/v1/agents/{inst['id']}/config/versions").json()
    assert [(v["version"], v["status"]) for v in versions] == [(2, "draft"), (1, "withdrawn")]


def test_a_change_behind_the_api_voids_the_review_and_the_execution_guard(owner, db):
    setup_company(owner)
    inst, cfg = submitted(owner)
    task = db.scalar(select(TaskDefinition).where(TaskDefinition.configuration_id == uuid.UUID(cfg["id"])))
    task.required_permissions = ["data.read", "comms.external"]
    db.commit()
    r = decide(owner, cfg)
    assert r.status_code == 409 and r.json()["error"]["code"] == "config_changed"
    task.required_permissions = ["data.read", "records.draft"]
    db.commit()
    assert decide(owner, cfg).status_code == 200
    # Phase 4 will move agents to active; simulate that to exercise the guard Phase 5 tools will call.
    inst_row = db.get(AgentInstance, uuid.UUID(inst["id"]))
    inst_row.status, inst_row.deployment_stage = "active", "full"
    db.commit()
    assert agent_service.execution_allowed(db, inst_row) == (True, "Approved configuration v1, full permissions")
    db.get(AgentConfiguration, uuid.UUID(cfg["id"])).config = {**cfg["config"], "automation_level": "autonomous"}
    db.commit()
    db.refresh(inst_row)
    assert agent_service.execution_allowed(db, inst_row) == (False, "The configuration changed after it was approved")


def test_unapproved_agents_never_pass_the_execution_guard(owner, db):
    setup_company(owner)
    inst, _ = submitted(owner)
    row = db.get(AgentInstance, uuid.UUID(inst["id"]))
    row.status = "active"  # even if a status were forced, there is no approval for this configuration
    db.commit()
    allowed, reason = agent_service.execution_allowed(db, row)
    assert not allowed and reason == "The current configuration has not been approved"


def test_schedule_preview_in_company_timezone(owner):
    setup_company(owner)
    inst, _ = generated(owner)
    r = owner.get(f"/api/v1/agents/{inst['id']}/schedule")
    assert r.status_code == 200
    preview = r.json()
    review = next(t for t in preview["tasks"] if t["key"] == "review-outstanding-invoices")
    assert len(review["next_runs"]) == 5
    assert all(run.endswith("08:00:00+00:00") for run in review["next_runs"])  # 16:00 Manila
    assert any("business hours" in n for n in preview["notes"])
    expense = next(t for t in preview["tasks"] if t["key"] == "expense-categorisation")
    assert expense["event"] == "expense.submitted" and expense["next_runs"] == []


# ---- confirmed rules feed the configuration ----------------------------------------------------------------------

def test_confirmed_rules_are_applied_and_open_ones_only_listed(owner):
    setup_company(owner)
    rule = owner.post("/api/v1/rules", json={
        "title": "Refund approval", "kind": "threshold", "applies_to": ["finance", "support"],
        "statement": "Refunds above 5,000 PHP require written approval from the Finance Manager."}).json()
    assert rule["status"] == "confirmed" and rule["threshold_amount"] == "5000.00"
    owner.post("/api/v1/rules", json={"title": "HR only", "statement": "Leave needs 7 days notice.",
                                      "applies_to": ["hr"]})
    _, cfg = generated(owner)
    assert cfg["generation"]["rules_used"] == [rule["id"]]
    assert "Refunds above 5,000 PHP require written approval from the Finance Manager." in \
        cfg["config"]["job"]["approval_requirements"]  # the HR-only rule is not applied to Finance


# ---- model refinement (real-provider path, with a fake model) ---------------------------------------------------

def test_model_refines_text_but_never_permissions_and_is_verified(owner, monkeypatch):
    setup_company(owner)
    from abos.agents import design

    def fake(caller, *, purpose, system, user, schema, dev, analysis=False):
        assert purpose == "agent_design" and "untrusted data" in system
        return gateway.LLMResult({
            "mission": "Cut overdue receivables by 47% this quarter.",  # 47 appears nowhere → keep template
            "scope": "Finance support for Acme Trading's receivables and expenses.",
            "included_tasks": ["Review invoices and receivables", "Prepare financial summaries"],
            "escalation_policies": ["Escalate unusual transactions to the CEO"],
            "success_metrics": ["Overdue receivables flagged within one business day: 100%"],
            "task_text": [{"key": "review-outstanding-invoices", "description": "Check every open invoice daily.",
                           "expected_output": "A ranked list of overdue invoices."}],
            "extra_tasks": [{"title": "Answer a finance question", "description": "On request.",
                             "expected_output": "A cited answer."}],
            "citations": [{"source": "S1", "quote": "this text is not in any source"}],
            "permissions": {"finance.execute": "auto"},  # outside the schema: must be ignored
        }, "anthropic", "claude-opus-5-5", False, None)

    monkeypatch.setattr(design.gateway, "complete_json", fake)
    inst, cfg = generated(owner)
    job = cfg["config"]["job"]
    assert job["mission"] != "Cut overdue receivables by 47% this quarter."
    assert job["scope"] == "Finance support for Acme Trading's receivables and expenses."
    assert cfg["config"]["permissions"]["finance.execute"] == "denied"
    warnings = cfg["generation"]["warnings"]
    assert any("47" in w for w in warnings) and any("Dropped a citation" in w for w in warnings)
    assert cfg["generation"]["citations"] == [] and cfg["generation"]["is_dev"] is False
    review = next(t for t in cfg["tasks"] if t["key"] == "review-outstanding-invoices")
    assert review["description"] == "Check every open invoice daily."
    assert review["trigger_type"] == "schedule" and review["schedule"]["time"] == "16:00"
    extra = next(t for t in cfg["tasks"] if t["key"] == "answer-a-finance-question")
    assert extra["trigger_type"] == "on_demand" and extra["required_permissions"] == ["data.read"]
    assert not [i for i in cfg["issues"] if i["severity"] == "error"]


# ---- tenancy & roles ---------------------------------------------------------------------------------------------

def test_other_tenants_cannot_see_or_act_on_agents(owner, rival, app_db):
    setup_company(owner)
    inst, cfg = submitted(owner)
    for r in (rival.get(f"/api/v1/agents/{inst['id']}"),
              rival.post(f"/api/v1/agents/{inst['id']}/config/generate"),
              rival.put(f"/api/v1/agents/{inst['id']}/config/draft", json=draft_body(cfg)),
              rival.get(f"/api/v1/agents/{inst['id']}/config/versions"),
              rival.get(f"/api/v1/approvals/configurations/{cfg['id']}"),
              decide(rival, cfg)):
        assert r.status_code == 404, r.text
    assert rival.get("/api/v1/agents").json() == []
    assert rival.get("/api/v1/approvals/pending").json() == []
    assert all(d["status"] == "available" for d in rival.get("/api/v1/agents/catalog").json())
    assert app_db.scalars(select(AgentInstance)).all() == []  # RLS: no tenant bound → nothing
    set_tenant(app_db, uuid.UUID(rival.org_id))
    assert app_db.scalars(select(AgentConfiguration)).all() == []


def test_viewers_read_but_cannot_configure(owner):
    setup_company(owner)
    inst = hire(owner)
    viewer = join(owner, "viewer@acme.example.com", "viewer")
    assert viewer.get(f"/api/v1/agents/{inst['id']}").status_code == 200
    assert viewer.get("/api/v1/agents/recommendation").status_code == 200
    assert viewer.post(f"/api/v1/agents/{inst['id']}/config/generate").status_code == 403
    assert viewer.post(f"/api/v1/agents/{inst['id']}/retire").status_code == 403
    manager = join(owner, "manager@acme.example.com", "manager")
    assert manager.post(f"/api/v1/agents/{inst['id']}/config/generate").status_code == 200
