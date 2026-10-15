"""Phase 6: daily reports from execution records, attempted vs completed vs unverified + reconciliation,
notifications (recipients by permission, preferences, limits, retries, digests, SMS adapter), Control Center,
usage & cost tracking and enforced budgets."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from abos.core.config import get_settings
from abos.identity.models import EmailOutbox
from abos.llm.models import ModelUsage
from abos.notifications import channels
from abos.notifications import service as notifications
from abos.notifications.models import Notification, NotificationDelivery
from abos.orchestration import scheduler
from abos.orchestration.models import WorkflowRun
from abos.reporting import service as reporting
from abos.reporting.models import DailyReport, ReportEvidence
from abos.tools import reconcile
from abos.tools.models import ToolExecution
from tests.conftest import OwnerSession, join
from tests.test_agents_api import setup_company
from tests.test_execution import TODAY, active, can_send, d, invoice, start, steps


def approve_pending(actor):
    for req in actor.get("/api/v1/approvals/actions").json():
        r = actor.post(f"/api/v1/approvals/actions/{req['id']}/decide",
                       json={"decision": "approved", "params_hash": req["params_hash"]})
        assert r.status_code == 200, r.text


def report_today(actor, inst):
    r = actor.post("/api/v1/reports/generate", json={"agent_id": inst["id"]})
    assert r.status_code == 201, r.text
    return actor.get(f"/api/v1/reports/{r.json()['id']}").json()


# ---- daily reports -----------------------------------------------------------------------------------------------

def test_daily_report_is_built_from_execution_records(owner, db):
    setup_company(owner)
    invoice(owner, "INV-1", due=d(-40), lines=(("Audit", "1", "4000.00"),))
    invoice(owner, "INV-2", due=d(-5), lines=(("A", "1", "10000.00"), ("B", "1", "2000.00")),
            recorded_total="12500.00", source="import")
    inst, _ = active(owner, edit=can_send)
    held = start(owner, inst, "review-outstanding-invoices")
    assert held["status"] == "awaiting_approval"
    early = report_today(owner, inst)
    assert set(early["content"]) == set(reporting.SECTIONS)
    assert early["final"] is False and early["counts"]["awaiting_approval"] == 2  # the run + its pending action
    assert early["content"]["awaiting_approval"][1]["action"] == "Send approved payment reminders"
    approve_pending(owner)
    request = start(owner, inst, request="Anything overdue?")
    rep = report_today(owner, inst)
    assert rep["version"] == 2 and rep["id"] == early["id"]
    c = rep["content"]
    assert [x["run_id"] for x in c["completed"]] == [held["id"], request["id"]], owner.get(f"/api/v1/workflows/{held['id']}").json()["validation"]
    assert c["agent"]["timezone"] == "Asia/Manila" and c["agent"]["date"] == TODAY.isoformat()
    assert {t["key"] for t in c["assigned"]} >= {"review-outstanding-invoices", "request"}
    # attempted vs completed: every executed call counted once, the held attempt is "not run"
    review = owner.get(f"/api/v1/workflows/{held['id']}").json()
    ran = [x for x in review["executions"] + owner.get(f"/api/v1/workflows/{request['id']}").json()["executions"]
           if x["status"] in ("succeeded", "unverified", "failed")]
    assert c["outcomes"]["attempted"] == len(ran) == c["outcomes"]["completed"]
    assert c["outcomes"]["not_run"] == 1 and c["outcomes"]["unverified"] == 0
    assert c["actions"]["per_tool"]["reminder.send"] == {"attempted": 1, "succeeded": 1, "unverified": 0,
                                                         "failed": 0, "not_run": 1}
    assert [e["severity"] for e in c["escalations"]] == ["high"]  # INV-2's discrepancy
    assert c["costs"]["dev_calls"] > 0 and c["costs"]["model_cost_usd"] == "0.0000" and c["costs"]["label"]
    assert c["kpis"]["defined"][0]["value"] is None  # no measurement source: said so, not invented
    assert any(u["task"] == "Review outstanding invoices" for u in c["upcoming"])
    refs = {(e["section"], e["ref_id"]) for e in rep["evidence"]}
    assert ("completed", held["id"]) in refs and ("escalations", steps(review, "escalate")[0]["id"]) in refs
    assert "2 completed" in rep["summary"]
    # The scheduler closes the day: a final report + a "report ready" notification, once.
    tomorrow = datetime.now(UTC) + timedelta(days=1)
    with OwnerSession() as s:
        row = s.get(WorkflowRun, uuid.UUID(held["id"]))
        inst_row = s.get(type(row).__mapper__.relationships and None or __import__(
            "abos.agents.models", fromlist=["AgentInstance"]).AgentInstance, row.instance_id)
        assert reporting.due_reports(s, tomorrow) == 1
        s.commit()
        assert reporting.due_reports(s, tomorrow) == 0
        final = s.scalar(select(DailyReport).where(DailyReport.instance_id == inst_row.id))
        assert final.final is True and final.version == 3
        assert s.scalar(select(Notification).where(Notification.kind == "report_ready")).link == \
            f"/app/reports/{final.id}"
    listed = owner.get("/api/v1/reports").json()
    assert [r["final"] for r in listed] == [True]
    viewer = join(owner, "viewer@acme.example.com", "viewer")
    assert viewer.get("/api/v1/reports").status_code == 200
    assert viewer.get(f"/api/v1/reports/{rep['id']}").status_code == 403  # content quotes records


def test_unverified_send_is_reported_unverified_until_reconciled(owner, db):
    setup_company(owner)
    inst, _ = active(owner)
    run = start(owner, inst, request="anything")
    outbox = EmailOutbox(to_email="ap@customer.example.com", subject="Reminder", body="…", provider="smtp",
                         status="queued")
    db.add(outbox)
    db.flush()
    db.add(ToolExecution(organization_id=uuid.UUID(owner.org_id), run_id=uuid.UUID(run["id"]),
                         instance_id=uuid.UUID(inst["id"]), step_no=9, tool="reminder.send", registry_version="t",
                         scope="comms.external", risk="high", input={}, input_hash="x", decision="executed",
                         reason="Queued for SMTP delivery", status="unverified", planner="playbook",
                         output={"delivery": {"adapter": "smtp", "outbox_id": str(outbox.id)}},
                         started_at=datetime.now(UTC), finished_at=datetime.now(UTC)))
    db.commit()
    rep = report_today(owner, inst)
    assert rep["content"]["outcomes"]["unverified"] == 1 and rep["counts"]["verified"] < rep["counts"]["attempted"]
    assert "with unknown outcome" in rep["summary"]
    assert reconcile.reconcile(db) == {"confirmed": 0, "failed": 0}  # still queued: nothing learned yet
    outbox.status, outbox.sent_at = "sent", datetime.now(UTC)
    db.commit()
    assert reconcile.reconcile(db) == {"confirmed": 1, "failed": 0}
    assert reconcile.reconcile(db) == {"confirmed": 0, "failed": 0}  # once
    db.commit()
    rep = report_today(owner, inst)
    o = rep["content"]["outcomes"]
    assert o["unverified"] == 0 and o["reconciled"][0]["outcome"] == "confirmed" and o["completed"] == o["attempted"]
    row = db.scalar(select(ToolExecution).where(ToolExecution.step_no == 9))
    db.refresh(row)
    assert row.status == "unverified"  # the ledger itself is never rewritten


# ---- notifications -----------------------------------------------------------------------------------------------

def test_notifications_by_permission_with_preferences_limits_retries_and_digests(owner, rival, db, monkeypatch):
    setup_company(owner)
    manager = join(owner, "manager@acme.example.com", "manager")
    viewer = join(owner, "viewer@acme.example.com", "viewer")
    assert owner.put("/api/v1/notifications/preferences", json={
        "email_immediate": "warning", "sms_critical": True, "sms_number": "+639171234567",
        "digest_time": "23:59"}).status_code == 200
    assert manager.put("/api/v1/notifications/preferences", json={"digest_time": "23:59"}).status_code == 200
    assert owner.put("/api/v1/notifications/preferences", json={"sms_critical": True}).status_code == 422
    invoice(owner, "INV-9", due=d(-70), lines=(("A", "1", "10000.00"), ("B", "1", "2000.00")),
            recorded_total="12500.00", source="import")
    invoice(owner, "INV-10", due=d(-40))
    inst, _ = active(owner, edit=can_send)
    run = start(owner, inst, "review-outstanding-invoices")
    mine = {n["kind"] for n in owner.get("/api/v1/notifications").json()}
    assert {"action_required", "escalation"} <= mine  # the owner decides approvals and manages tasks
    # The manager manages tasks (escalations) but can't decide approvals, so isn't asked to.
    assert {n["kind"] for n in manager.get("/api/v1/notifications").json()} == {"escalation"}
    approve_pending(owner)
    assert viewer.get("/api/v1/notifications").json() == []
    assert rival.get("/api/v1/notifications").json() == []
    # The owner chose immediate email for warnings: the approval request went out at once (dev outbox, labelled).
    sent = {x["kind"]: x for x in owner.get("/api/v1/notifications/deliveries").json()}
    assert sent["alert"]["status"] == "stored" and sent["alert"]["provider"] == "dev_outbox"
    assert "not delivered" in sent["alert"]["last_error"]
    # Same event twice → one notification.
    with OwnerSession() as s:
        before = s.scalar(select(Notification).where(Notification.kind == "action_required"))
        assert notifications.notify(s, before.organization_id, kind="action_required", severity="warning",
                                    title="x", body="x", dedupe=before.dedupe_key) == []
        # A critical alert reaches the owner by email and by SMS through the (dev) SMS adapter.
        notifications.notify(s, before.organization_id, kind="run_unverified", severity="critical",
                             title="Outcome unknown", body="A send timed out", link=f"/app/tasks/{run['id']}",
                             dedupe="t-critical")
        s.commit()
    owner_id = uuid.UUID(owner.user_id)
    rows = db.scalars(select(NotificationDelivery).where(NotificationDelivery.user_id == owner_id)).all()
    sms = [x for x in rows if x.channel == "sms"]
    assert len(sms) == 1 and (sms[0].status, sms[0].provider) == ("stored", "dev_sms")
    # Delivery limit: over the hourly email limit an alert is suppressed (it stays in the digest).
    monkeypatch.setattr(get_settings(), "notify_email_per_hour", 1)
    with OwnerSession() as s:
        notifications.notify(s, before.organization_id, kind="run_failed", severity="warning", title="Failed",
                             body="x", dedupe="t-limit")
        s.commit()
    limited = db.scalar(select(NotificationDelivery).join(Notification).where(Notification.dedupe_key == "t-limit",
                                                                               NotificationDelivery.user_id == owner_id))
    assert limited.status == "suppressed" and "Delivery limit" in limited.last_error
    # A failing provider is retried with backoff, then abandoned.
    monkeypatch.setattr(get_settings(), "notify_email_per_hour", 100)
    monkeypatch.setattr(get_settings(), "notify_max_attempts", 2)
    monkeypatch.setattr(channels, "send_email", lambda *a, **k: (_ for _ in ()).throw(ConnectionError("down")))
    with OwnerSession() as s:
        notifications.notify(s, before.organization_id, kind="run_failed", severity="warning", title="Retry me",
                             body="x", dedupe="t-retry")
        s.commit()
    failing = db.scalar(select(NotificationDelivery).join(Notification).where(Notification.dedupe_key == "t-retry",
                                                                               NotificationDelivery.user_id == owner_id))
    assert (failing.status, failing.attempts) == ("failed", 1) and failing.next_attempt_at
    assert scheduler.tick(failing.next_attempt_at + timedelta(seconds=1))["retried"] >= 1
    db.refresh(failing)
    assert (failing.status, failing.attempts) == ("abandoned", 2) and "down" in failing.last_error
    monkeypatch.undo()
    # Digest: once a day at the user's digest time (company time zone), with everything not yet digested.
    late = datetime.combine(TODAY, datetime.min.time(), UTC) + timedelta(hours=15, minutes=59, seconds=30)
    assert scheduler.tick(late - timedelta(minutes=10))["digests"] == 0  # 23:49 Manila: before the digest time
    assert scheduler.tick(late)["digests"] == 2  # 23:59:30 Manila: owner + manager
    assert scheduler.tick(late + timedelta(seconds=20))["digests"] == 0  # once a day
    digest = db.scalar(select(NotificationDelivery).where(NotificationDelivery.user_id == owner_id,
                                                          NotificationDelivery.kind == "digest"))
    assert "Approval needed" in digest.body and digest.status == "stored"
    # Reading.
    count = owner.get("/api/v1/notifications/unread-count").json()["unread"]
    first_id = owner.get("/api/v1/notifications").json()[0]["id"]
    assert owner.post(f"/api/v1/notifications/{first_id}/read").json() == {"marked": 1}
    assert owner.get("/api/v1/notifications/unread-count").json()["unread"] == count - 1
    assert rival.post(f"/api/v1/notifications/{first_id}/read").status_code == 404
    assert owner.post("/api/v1/notifications/read-all").json()["marked"] == count - 1


# ---- Control Center, usage, budgets ------------------------------------------------------------------------------

def test_control_center_usage_and_budget_enforcement(owner, db):
    setup_company(owner)
    invoice(owner, "INV-20", due=d(-5), lines=(("A", "1", "10000.00"), ("B", "1", "2000.00")),
            recorded_total="12500.00", source="import")
    inst, _ = active(owner)
    review = start(owner, inst, "review-outstanding-invoices")
    start(owner, inst, request="status?")
    with OwnerSession() as s:  # the review took longer than its 120-minute SLA
        r = s.get(WorkflowRun, uuid.UUID(review["id"]))
        r.started_at = r.finished_at - timedelta(minutes=180)
        s.commit()
    cc = owner.get("/api/v1/dashboard").json()
    assert cc["agents"]["total"] == 1 and cc["agents"]["active"] == 1
    assert (cc["tasks"]["assigned"], cc["tasks"]["completed"], cc["tasks"]["overdue"]) == (2, 2, 1)
    assert cc["overdue"][0]["run_id"] == review["id"] and cc["overdue"][0]["priority"] == "high"
    assert cc["escalations"][0]["severity"] == "high"
    perf = cc["performance"][0]
    assert (perf["runs"], perf["completed"], perf["completion_rate"]) == (2, 2, 1.0)
    assert cc["options"]["departments"] == ["Finance"]
    assert owner.get("/api/v1/dashboard?priority=high").json()["tasks"]["assigned"] == 1
    assert owner.get("/api/v1/dashboard?status=failed").json()["tasks"]["assigned"] == 0
    assert owner.get("/api/v1/dashboard?department=Sales").json()["agents"]["total"] == 0
    past = (TODAY - timedelta(days=30)).isoformat()
    assert owner.get(f"/api/v1/dashboard?date_from={past}&date_to={past}").json()["tasks"]["assigned"] == 0
    # Usage: the ledger is the source; dev calls are counted and labelled, they cost nothing.
    u = owner.get("/api/v1/usage").json()
    assert u["dev_calls"] > 0 and u["total_cost_usd"] == "0.0000" and u["dev_label"]
    assert u["agent_budgets"][0]["budget_usd"] == "60.00" and u["agent_budgets"][0]["over"] is False
    db.add(ModelUsage(organization_id=uuid.UUID(owner.org_id), purpose="workflow_step", provider="anthropic",
                      model="claude-opus-5-5", input_tokens=1000, output_tokens=500, cost_usd=Decimal("61.5"),
                      agent_instance_id=uuid.UUID(inst["id"])))
    db.commit()
    u = owner.get("/api/v1/usage").json()
    agent = next(a for a in u["by_agent"] if a["instance_id"] == inst["id"])
    assert agent["cost_usd"] == "61.5000" and u["agent_budgets"][0]["over"] is True
    assert u["company_budget"] == {"amount": "300.00", "currency": "USD", "comparable": True,
                                   "spent_usd": "61.5000", "over": False}
    # Budget reached: the next run is skipped and the people who read usage are told, once.
    skipped = start(owner, inst, request="one more")
    assert skipped["status"] == "skipped" and "Monthly AI budget reached" in skipped["status_reason"]
    start(owner, inst, request="and another")
    budget = [n for n in owner.get("/api/v1/notifications").json() if n["kind"] == "budget"]
    assert len(budget) == 1 and budget[0]["link"] == "/app/usage"
    manager = join(owner, "manager@acme.example.com", "manager")
    assert manager.get("/api/v1/usage").status_code == 403
    assert manager.get("/api/v1/dashboard").status_code == 200
    assert db.scalar(select(ReportEvidence.id)) is None  # nothing reported yet: reports are only built when asked/due
