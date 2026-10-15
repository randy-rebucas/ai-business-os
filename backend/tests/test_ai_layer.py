"""LLM gateway, jobs and the business interview."""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from abos.core.config import get_settings
from abos.jobs import service as jobs
from abos.knowledge.models import JobRun
from abos.llm import gateway
from abos.llm.embeddings import hash_embed
from abos.llm.models import ModelUsage
from tests.conftest import join, upload
from tests.fixtures import REFUND_POLICY


class FakeMessages:
    def __init__(self, response):
        self.response, self.kwargs = response, None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return self.response


def _fake_client(monkeypatch, response):
    messages = FakeMessages(response)
    monkeypatch.setattr(gateway, "_anthropic_client", lambda: SimpleNamespace(beta=SimpleNamespace(messages=messages)))
    s = get_settings()
    monkeypatch.setattr(s, "llm_provider", "anthropic")
    monkeypatch.setattr(s, "anthropic_api_key", SimpleNamespace(get_secret_value=lambda: "test-key"))
    return messages


def _response(stop_reason="end_turn", text='{"ok": true}'):
    return SimpleNamespace(stop_reason=stop_reason, content=[SimpleNamespace(type="text", text=text)],
                           usage=SimpleNamespace(input_tokens=1200, output_tokens=300), _request_id="req_test")


def test_anthropic_adapter_request_shape_and_usage_ledger(owner, monkeypatch, db):
    messages = _fake_client(monkeypatch, _response())
    caller = gateway.Caller(org_id=uuid.UUID(owner.org_id))
    result = gateway.complete_json(caller, purpose="rag_answer", system="sys", user="question",
                                   schema={"type": "object"}, dev=lambda: pytest.fail("dev path used"))
    assert result.data == {"ok": True} and not result.is_dev and result.label is None
    kw = messages.kwargs
    assert kw["model"] == "claude-opus-5-5"
    assert kw["output_config"]["format"] == {"type": "json_schema", "schema": {"type": "object"}}
    assert kw["output_config"]["effort"] == "medium"
    assert kw["betas"] == ["server-side-fallback-2026-07-01"] and kw["extra_body"] == {"fallbacks": "default"}
    assert "thinking" not in kw and "temperature" not in kw  # Opus 5.5: thinking always on, sampling params removed
    usage = db.scalar(select(ModelUsage).where(ModelUsage.provider == "anthropic"))
    assert (usage.input_tokens, usage.output_tokens, usage.request_id) == (1200, 300, "req_test")
    assert float(usage.cost_usd) == pytest.approx((1200 * 4 + 300 * 20) / 1_000_000)


@pytest.mark.parametrize("stop,code", [("refusal", "refusal"), ("max_tokens", "truncated")])
def test_anthropic_refusal_and_truncation_are_errors_and_recorded(owner, monkeypatch, db, stop, code):
    _fake_client(monkeypatch, _response(stop_reason=stop))
    with pytest.raises(gateway.LLMError) as exc:
        gateway.complete_json(gateway.Caller(uuid.UUID(owner.org_id)), purpose="x", system="", user="",
                              schema={}, dev=dict)
    assert exc.value.code == code
    row = db.scalar(select(ModelUsage).where(ModelUsage.provider == "anthropic"))
    assert row.status == ("refusal" if code == "refusal" else "error") and row.error_code == code


def test_invalid_json_from_model_is_an_error(owner, monkeypatch):
    _fake_client(monkeypatch, _response(text="not json"))
    with pytest.raises(gateway.LLMError, match="malformed"):
        gateway.complete_json(gateway.Caller(uuid.UUID(owner.org_id)), purpose="x", system="", user="",
                              schema={}, dev=dict)


def test_ask_maps_provider_errors_to_clean_api_errors(owner, monkeypatch):
    from tests.conftest import indexed

    indexed(owner, "refunds.md", REFUND_POLICY)
    _fake_client(monkeypatch, _response(stop_reason="refusal"))
    r = owner.post("/api/v1/knowledge/ask", json={"question": "Who approves refunds above the limit?"})
    assert r.status_code == 502 and r.json()["error"]["code"] == "ai_refusal"


def test_hash_embeddings_are_normalised_and_lexical():
    a, b, c = (hash_embed(t, 1024) for t in ("refund approval limit", "approval limit for refunds", "leave days"))
    dot = lambda x, y: sum(i * j for i, j in zip(x, y, strict=True))  # noqa: E731
    assert abs(dot(a, a) - 1) < 1e-9 and dot(a, b) > dot(a, c)


def test_production_refuses_dev_adapters():
    from abos.core.config import Settings

    with pytest.raises(ValueError, match="Development AI adapters"):
        Settings(env="production", cookie_secure=True, session_cookie_name="__Host-x", app_base_url="https://x",
                 database_url="postgresql+psycopg://u:p@h/db", mailer="smtp", smtp_host="smtp")


# ---- jobs ------------------------------------------------------------------------------------------------------

def test_sweeper_requeues_stuck_jobs_and_fails_exhausted_ones(owner, db):
    doc = upload(owner, "refunds.md", REFUND_POLICY)
    job = db.scalars(select(JobRun).where(JobRun.target_id == doc["id"])).one()
    old = datetime.now(UTC) - timedelta(hours=2)
    job.status, job.heartbeat_at, job.attempts = "running", old, job.max_attempts
    db.commit()
    assert jobs.sweep()["failed"] == 1
    db.refresh(job)
    assert job.status == "failed" and "Timed out" in job.last_error


def test_duplicate_delivery_does_not_run_a_job_twice(owner, db):
    doc = upload(owner, "refunds.md", REFUND_POLICY)
    job = db.scalars(select(JobRun).where(JobRun.target_id == doc["id"])).one()
    assert jobs.run_job(job.id) == "skipped"  # already succeeded


# ---- interview -------------------------------------------------------------------------------------------------

def test_interview_generates_follow_ups_from_gaps_and_content(owner):
    owner.post("/api/v1/company/processes", json={"name": "Purchase orders"})
    owner.post("/api/v1/company/software", json={"name": "QuickBooks", "category": "accounting",
                                                 "integration_wanted": True})
    r = owner.post("/api/v1/interview/generate")
    assert r.status_code == 200
    body = r.json()
    keys = {q["topic_key"] for q in body["questions"]}
    assert "gap:objectives" in keys and "docs:policies" in keys
    assert any(k.startswith("process-approval:") for k in keys) and any(k.startswith("software-access:") for k in keys)
    assert "gap:processes" not in keys  # a process exists, so that section is no longer a gap
    assert body["label"].startswith("Development adapter")
    # Regenerating doesn't duplicate.
    assert owner.post("/api/v1/interview/generate").json()["created"] == 0
    q = next(q for q in body["questions"] if q["topic_key"].startswith("process-approval:"))
    r = owner.post(f"/api/v1/interview/{q['id']}/answer", json={"answer": "Ops lead up to 50k, CEO above."})
    assert r.json()["status"] == "answered"
    assert owner.post(f"/api/v1/interview/{q['id']}/dismiss").status_code == 409


def test_interview_uses_model_questions_when_available(owner, monkeypatch):
    _fake_client(monkeypatch, _response(text='{"questions": [{"section": "processes", "question": "What refund '
                                             'amount needs your personal approval?", "rationale": "limits"}]}'))
    body = owner.post("/api/v1/interview/generate").json()
    model_qs = [q for q in body["questions"] if q["source"] == "model"]
    assert len(model_qs) == 1 and body["label"] is None


def test_interview_permissions(owner):
    viewer = join(owner, "viewer@acme.example.com", "viewer")
    assert viewer.get("/api/v1/interview").status_code == 200
    assert viewer.post("/api/v1/interview/generate").status_code == 403
