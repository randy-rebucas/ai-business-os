"""Business rule extraction & review (SPEC §3 step 4): facts / proposed / confirmed / unresolved / conflicting, each
traceable to a verified source; nothing enforced without confirmation."""

import uuid

import pytest

from abos.core.db import SessionLocal
from abos.core.tenancy import set_tenant
from abos.governance import rules as rules_module
from abos.llm import gateway
from tests.conftest import indexed, join
from tests.fixtures import INJECTED, LEAVE_POLICY, REFUND_POLICY, REFUND_POLICY_OLD
from tests.test_agents_api import HOURS


def extract(actor):
    r = actor.post("/api/v1/rules/extract")
    assert r.status_code == 200, r.text
    return r.json()


def rules(actor, status=None):
    return actor.get("/api/v1/rules" + (f"?status={status}" if status else "")).json()


def by_statement(items, fragment):
    return next(r for r in items if fragment in r["statement"])


def test_document_rules_quote_their_source_and_parse_thresholds(owner):
    doc = indexed(owner, "refund-policy.md", REFUND_POLICY)
    report = extract(owner)
    assert report["created"] > 0 and report["provider"] == "dev" and "Development adapter" in report["label"]
    items = rules(owner)
    above = by_statement(items, "Refunds above 5,000 PHP")
    assert above["status"] == "proposed" and above["kind"] == "threshold"
    assert above["threshold_amount"] == "5000.00" and above["threshold_currency"] == "PHP"
    cite = above["citations"][0]
    assert cite["document_id"] == doc["id"] and cite["quote"] in REFUND_POLICY.replace("\n", " ")
    assert set(above["applies_to"]) >= {"finance", "support"}
    escalation = by_statement(items, "Disputed charges must be escalated")
    assert escalation["kind"] == "escalation" and escalation["status"] == "proposed"
    assert not [r for r in items if "This policy applies" in r["statement"]]  # not a rule
    assert not [r for r in items if r["statement"].startswith("Refund Policy >")]  # heading path stripped
    assert not [r for r in items if r["status"] == "confirmed"]  # nothing is enforced automatically
    # Both gap topics are covered by the document, so no "missing" questions.
    assert not [r for r in items if r["status"] == "unresolved"]


def test_re_extraction_is_idempotent_and_keeps_reviews(owner):
    indexed(owner, "refund-policy.md", REFUND_POLICY)
    first = extract(owner)
    above = by_statement(rules(owner), "Refunds above 5,000 PHP")
    owner.post(f"/api/v1/rules/{above['id']}/review", json={"decision": "confirm"})
    again = extract(owner)
    assert again["created"] == 0 and again["existing"] >= first["created"]
    assert by_statement(rules(owner), "Refunds above 5,000 PHP")["status"] == "confirmed"


def test_without_documents_gaps_become_unresolved_questions(owner):
    report = extract(owner)
    assert report["sources_considered"] == 0
    open_q = rules(owner, "unresolved")
    assert {r["kind"] for r in open_q} == {"threshold", "escalation"}


def test_conflicting_limits_from_two_documents_are_flagged_not_resolved(owner):
    indexed(owner, "refund-policy.md", REFUND_POLICY)
    indexed(owner, "refund-policy-2023.md", REFUND_POLICY_OLD)  # not marked as superseded: both are "current"
    report = extract(owner)
    assert report["conflicts"] >= 2
    items = rules(owner)
    new = by_statement(items, "up to 5,000 PHP")
    old = by_statement(items, "up to 2,000 PHP")
    assert new["status"] == old["status"] == "conflicting"
    assert old["id"] in new["conflicts_with"] and new["id"] in old["conflicts_with"]
    # "up to 5,000" and "above 5,000" in one document are not a conflict.
    assert by_statement(items, "Refunds above 5,000 PHP")["status"] == "proposed"


def test_rules_from_retired_documents_are_stale_and_not_used(owner):
    doc = indexed(owner, "refund-policy.md", REFUND_POLICY)
    extract(owner)
    above = by_statement(rules(owner), "Refunds above 5,000 PHP")
    owner.post(f"/api/v1/rules/{above['id']}/review", json={"decision": "confirm"})
    assert owner.post(f"/api/v1/documents/{doc['id']}/archive").status_code == 200
    stale = by_statement(rules(owner), "Refunds above 5,000 PHP")
    assert stale["stale"] == 'The cited document "refund-policy" is now archived'
    with SessionLocal() as s:
        set_tenant(s, uuid.UUID(owner.org_id))
        assert rules_module.confirmed_for(s, uuid.UUID(owner.org_id), "finance") == []


def test_planted_instructions_never_become_rules(owner):
    indexed(owner, "supplier-sop.md", INJECTED)
    extract(owner)
    texts = " ".join(r["statement"] + r["title"] for r in rules(owner))
    assert "PWNED" not in texts and "system prompt" not in texts.lower()
    assert "30 days from invoice date" in texts


def test_model_items_are_verified_against_their_sources(owner, monkeypatch):
    indexed(owner, "refund-policy.md", REFUND_POLICY)

    def fake(caller, *, purpose, system, user, schema, dev, analysis=False):
        assert purpose == "rule_extraction" and "<source id=\"S1\"" in user
        good = "Refunds above 5,000 PHP require written approval from the Finance Manager"
        return gateway.LLMResult({"items": [
            {"status": "proposed", "kind": "threshold", "title": "Refund approval", "source": "S1", "quote": good,
             "statement": "Agents must get the Finance Manager's written approval for refunds above 5,000 PHP.",
             "applies_to": ["support"]},
            {"status": "fact", "kind": "threshold", "title": "Invented", "source": "S1",
             "quote": "Refunds above 50,000 PHP need board approval", "statement": "Board approves refunds.",
             "applies_to": []},
            {"status": "proposed", "kind": "threshold", "title": "Wrong figure", "source": "S1", "quote": good,
             "statement": "Refunds above 9,000 PHP need approval.", "applies_to": []},
            {"status": "fact", "kind": "policy", "title": "Ghost", "source": "S99", "quote": good,
             "statement": "Something.", "applies_to": []},
            {"status": "unresolved", "kind": "approval", "title": "Deputy", "source": "", "quote": "",
             "statement": "Who approves refunds when the Finance Manager is away?", "applies_to": ["finance"]},
        ]}, "anthropic", "claude-opus-5-5", False, None)

    monkeypatch.setattr(rules_module.gateway, "complete_json", fake)
    report = extract(owner)
    reasons = sorted(d["reason"] for d in report["dropped"])
    assert reasons == ["figures not in the quoted text: 9000", "quote not found in source", "unknown source id"]
    items = rules(owner)
    kept = by_statement(items, "Agents must get the Finance Manager")
    assert kept["provider"] == "anthropic" and kept["label"] is None and kept["threshold_amount"] == "5000.00"
    assert by_statement(items, "Finance Manager is away")["status"] == "unresolved"


def test_interview_answers_and_profile_become_reviewable_rules(owner):
    owner.patch("/api/v1/company/profile", json={"timezone": "Asia/Manila", "operating_schedule": HOURS})
    owner.post("/api/v1/company/processes", json={"name": "Purchasing",
                                                  "approval_procedure": "Orders above $2,000 need the CEO."})
    owner.post("/api/v1/interview/generate")
    q = owner.get("/api/v1/interview").json()[0]
    owner.post(f"/api/v1/interview/{q['id']}/answer", json={"answer": "Discounts above 10% need my approval."})
    extract(owner)
    items = rules(owner)
    interview = next(r for r in items if r["source_type"] == "interview")
    assert interview["status"] == "proposed" and interview["statement"] == "Discounts above 10% need my approval."
    hours = next(r for r in items if r["kind"] == "operating_hours")
    assert hours["status"] == "fact" and "Asia/Manila" in hours["statement"] and "Mon 09:00–17:00" in hours["statement"]
    purchasing = next(r for r in items if r["source_type"] == "profile" and "Purchasing" in r["statement"])
    assert purchasing["status"] == "proposed" and purchasing["threshold_amount"] == "2000.00"


def test_review_confirm_reject_edit_and_policy_version(owner):
    extract(owner)  # gap questions only
    q = rules(owner, "unresolved")[0]
    r = owner.post(f"/api/v1/rules/{q['id']}/review", json={"decision": "confirm"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "resolution_required"
    with SessionLocal() as s:
        set_tenant(s, uuid.UUID(owner.org_id))
        before = rules_module.policy_version(s, uuid.UUID(owner.org_id))
    r = owner.post(f"/api/v1/rules/{q['id']}/review",
                   json={"decision": "confirm", "resolution": "Anything above $500 needs the CEO.",
                         "statement": "AI employees need the CEO's approval above $500."})
    confirmed = r.json()
    assert confirmed["status"] == "confirmed" and confirmed["threshold_amount"] == "500.00"
    assert confirmed["resolution"] == "Anything above $500 needs the CEO."
    with SessionLocal() as s:
        set_tenant(s, uuid.UUID(owner.org_id))
        assert rules_module.policy_version(s, uuid.UUID(owner.org_id)) != before
    other = rules(owner, "unresolved")[0]
    assert owner.post(f"/api/v1/rules/{other['id']}/review", json={"decision": "reject"}).json()["status"] == "rejected"


def test_rule_permissions_access_levels_and_tenancy(owner, rival):
    indexed(owner, "leave.md", LEAVE_POLICY, access_level="confidential")
    extract(owner)
    secret = by_statement(rules(owner), "15 days of paid annual leave")
    assert secret["access_level"] == "confidential"
    manager = join(owner, "manager@acme.example.com", "manager")
    assert all(r["id"] != secret["id"] for r in rules(manager))
    assert manager.post(f"/api/v1/rules/{secret['id']}/review", json={"decision": "reject"}).status_code == 404
    member = join(owner, "member@acme.example.com", "member")
    assert member.get("/api/v1/rules").status_code == 200
    assert member.post("/api/v1/rules/extract").status_code == 403
    assert member.post("/api/v1/rules", json={"title": "x rule", "statement": "Never do x."}).status_code == 403
    assert rival.get("/api/v1/rules").json() == []
    assert rival.post(f"/api/v1/rules/{secret['id']}/review", json={"decision": "confirm"}).status_code == 404


@pytest.mark.parametrize("text,expected", [
    ("Orders above $2,000 need the CEO.", "threshold"),
    ("All refunds are logged weekly.", "customer_service"),
])
def test_classify_examples(text, expected):
    assert rules_module.classify(text) == expected
