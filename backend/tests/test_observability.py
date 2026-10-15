"""Phase 7 observability: Prometheus metrics, the error-reporting hook (API and jobs), correlation ids in logs."""

import json
import logging
import uuid

from pydantic import SecretStr
from sqlalchemy import select

from abos.core import errors, metrics
from abos.core.config import get_settings
from abos.core.db import SessionLocal
from abos.core.logging import JsonFormatter, log_context
from abos.core.tenancy import set_tenant
from abos.jobs import service as jobs
from abos.knowledge.models import JobRun
from abos.main import app
from tests.conftest import indexed, new_client


def test_metrics_need_a_token_and_report_requests_and_background_work(owner, monkeypatch):
    s = get_settings()
    anonymous = new_client()
    assert anonymous.get("/api/metrics").status_code == 404  # disabled without a configured token
    monkeypatch.setattr(s, "metrics_token", SecretStr("scrape-token-123"))
    assert anonymous.get("/api/metrics").status_code == 401
    assert anonymous.get("/api/metrics", headers={"Authorization": "Bearer nope"}).status_code == 401
    metrics.reset_for_tests()
    indexed(owner, "faq.md", "# FAQ\n\nThe office opens at 9am.\n")
    owner.get(f"/api/v1/documents/{uuid.uuid4()}")  # a 404, counted under its route template
    r = anonymous.get("/api/metrics", headers={"Authorization": "Bearer scrape-token-123"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
    body = r.text
    assert 'abos_http_requests_total{method="POST",route="/api/v1/documents",status="201"} 1' in body
    assert 'route="/api/v1/documents/{doc_id}",status="404"' in body  # templates, never raw ids
    assert str(owner.org_id) not in body and "faq" not in body  # no tenant data in labels
    assert 'abos_http_request_duration_seconds_count{method="POST",route="/api/v1/documents"} 1' in body
    assert 'abos_jobs{kind="ingest_document",status="succeeded"} 1' in body
    assert 'abos_documents{status="awaiting_review"}' in body or 'abos_documents{status="indexed"} 1' in body
    assert "abos_jobs_oldest_queued_seconds 0" in body and "abos_database_up 1" in body
    for line in body.splitlines():  # valid exposition format: comments or `name{labels} value`
        assert line.startswith("#") or len(line.rsplit(" ", 1)) == 2, line


def test_unhandled_api_errors_are_reported_once_without_leaking(owner, monkeypatch):
    seen = []

    def boom():
        raise RuntimeError("database password is hunter2")

    app.add_api_route("/api/v1/_test/boom", boom, methods=["GET"])
    errors.add_reporter(lambda exc, fields: seen.append((type(exc).__name__, fields)))
    try:
        metrics.reset_for_tests()
        r = owner.client.get("/api/v1/_test/boom", headers={"X-Request-Id": "req-abc"})
    finally:
        errors._reporters.clear()
        app.router.routes[:] = [x for x in app.router.routes if getattr(x, "path", "") != "/api/v1/_test/boom"]
    assert r.status_code == 500
    assert r.json()["error"] == {"code": "internal_error", "message": r.json()["error"]["message"],
                                 "details": {"request_id": "req-abc"}}
    assert "hunter2" not in r.text
    assert len(seen) == 1 and seen[0][0] == "RuntimeError"
    assert seen[0][1]["route"] == "/api/v1/_test/boom" and seen[0][1]["where"] == "api"
    assert 'abos_unhandled_errors_total{where="api"} 1' in metrics.render()


def test_job_failures_are_reported_with_job_context(owner):
    seen = []
    errors.add_reporter(lambda exc, fields: seen.append(fields))
    jobs.HANDLERS["test_boom"] = lambda db, job: (_ for _ in ()).throw(ValueError("bad state"))
    try:
        with SessionLocal() as db:
            set_tenant(db, uuid.UUID(owner.org_id))
            job = jobs.enqueue(db, uuid.UUID(owner.org_id), "test_boom", uuid.uuid4())
            db.commit()  # eager mode: runs (and retries) after commit
            job_id = job.id
    finally:
        errors._reporters.clear()
        jobs.HANDLERS.pop("test_boom")
    with SessionLocal() as db:
        set_tenant(db, uuid.UUID(owner.org_id))
        final = db.scalar(select(JobRun).where(JobRun.id == job_id))
        assert final.status == "failed" and final.attempts == get_settings().job_max_attempts
    assert len(seen) == get_settings().job_max_attempts  # one report per failed attempt
    assert seen[-1]["job_id"] == str(job_id) and seen[-1]["job_kind"] == "test_boom"
    assert seen[-1]["org_id"] == owner.org_id and seen[-1]["where"] == "job" and seen[-1]["permanent"] is True


def test_log_lines_carry_request_and_job_correlation_ids(caplog):
    caplog.set_level(logging.INFO)
    with log_context(job_id="j-1", run_id="r-9"):
        logging.getLogger("abos.test").info("inside", extra={"fields": {"step": "plan"}})
    logging.getLogger("abos.test").info("outside")
    inside, outside = (json.loads(JsonFormatter().format(r)) for r in caplog.records[-2:])
    assert (inside["job_id"], inside["run_id"], inside["step"]) == ("j-1", "r-9", "plan")
    assert "job_id" not in outside
