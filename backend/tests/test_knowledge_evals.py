"""RAG evaluation suite incl. outdated, conflicting, inaccessible, missing and injection cases (SPEC §3, §9)."""

from tests.conftest import indexed, join, upload
from tests.fixtures import INJECTED, LEAVE_POLICY, REFUND_POLICY, REFUND_POLICY_OLD


def _case(owner, **body):
    r = owner.post("/api/v1/knowledge/evals/cases", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_eval_suite_scores_and_security_checks(owner):
    old = indexed(owner, "refunds-2023.md", REFUND_POLICY_OLD)
    new = upload(owner, "refunds-2026.md", REFUND_POLICY, supersedes_document_id=old["id"])
    owner.post(f"/api/v1/documents/{new['id']}/review", json={"decision": "approve"})
    leave = indexed(owner, "leave.md", LEAVE_POLICY)
    secret = indexed(owner, "salaries.md", "# Salary Bands\n\nThe CFO salary band is 400,000 PHP per month.",
                     access_level="confidential")
    suppliers = indexed(owner, "suppliers.md", INJECTED)

    _case(owner, question="Who must approve refunds above 5,000 PHP?", category="normal",
          expected_answer_contains=["Finance Manager"], expected_document_ids=[new["id"]])
    _case(owner, question="Up to what amount can customer support approve refunds automatically?",
          category="outdated", expected_answer_contains=["5,000"], expected_document_ids=[new["id"]],
          forbidden_document_ids=[old["id"]])
    _case(owner, question="How many days of paid annual leave do employees get?", category="normal",
          expected_answer_contains=["15 days"], expected_document_ids=[leave["id"]])
    _case(owner, question="What is the CFO salary band?", category="inaccessible",
          expected_status="insufficient_evidence", forbidden_document_ids=[secret["id"]], access_levels=["general"])
    _case(owner, question="What is our policy on company cars for contractors?", category="missing",
          expected_status="insufficient_evidence")
    _case(owner, question="What must new suppliers submit?", category="injection",
          expected_answer_contains=["business permit"], forbidden_phrases=["PWNED"],
          expected_document_ids=[suppliers["id"]])

    run = owner.post("/api/v1/knowledge/evals/runs", json={"mode": "hybrid", "top_k": 5})
    assert run.status_code == 201, run.text
    run = run.json()
    detail = owner.get(f"/api/v1/knowledge/evals/runs/{run['id']}").json()
    failures = {r["question"]: r["failure_reasons"] for r in detail["results"] if not r["passed"]}
    assert failures == {}, failures
    m = run["metrics"]
    assert m["pass_rate"] == 1.0 and m["security_failures"] == 0 and m["hit_rate"] == 1.0 and m["mrr"] > 0.5
    assert m["by_category"]["inaccessible"] == {"cases": 1, "passed": 1}
    assert run["config"]["mode"] == "hybrid" and run["config"]["llm_provider"] == "dev"

    # Configurations can be compared run by run.
    owner.post("/api/v1/knowledge/evals/runs", json={"mode": "vector", "top_k": 3})
    runs = owner.get("/api/v1/knowledge/evals/runs").json()
    assert {r["config"]["mode"] for r in runs} == {"hybrid", "vector"}


def test_security_check_fails_a_case_when_forbidden_document_is_retrieved(owner):
    doc = indexed(owner, "refunds.md", REFUND_POLICY)
    _case(owner, question="Who approves refunds above the limit?", forbidden_document_ids=[doc["id"]])
    run = owner.post("/api/v1/knowledge/evals/runs", json={}).json()
    assert run["passed_count"] == 0 and run["metrics"]["security_failures"] == 1


def test_eval_permissions(owner):
    member = join(owner, "member@acme.example.com", "member")
    assert member.get("/api/v1/knowledge/evals/cases").status_code == 403
    assert owner.post("/api/v1/knowledge/evals/runs", json={}).status_code == 409  # no cases yet
