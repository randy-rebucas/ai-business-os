"""Phase 5: tool registry, business records, orchestrated execution with evidence, approvals bound to exact
parameters, scheduling, events, idempotency, retries, unknown outcomes, delegation, tenancy."""

import dataclasses
import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, ProgrammingError

from abos.core.tenancy import set_tenant
from abos.identity.models import EmailOutbox
from abos.jobs import service as jobs
from abos.llm import gateway
from abos.orchestration import planner, scheduler
from abos.orchestration import service as orchestration
from abos.orchestration.models import WorkflowRun
from abos.tools import handlers, registry
from abos.tools.models import ToolExecution
from tests.conftest import join
from tests.test_agents_api import setup_company
from tests.test_simulation import approved, run

TODAY = datetime.now(ZoneInfo("Asia/Manila")).date()  # the test company's time zone (setup_company)


def d(days: int) -> str:
    return (TODAY + timedelta(days=days)).isoformat()


def invoice(actor, number, *, due, lines=(("Consulting", "1", "1000.00"),), email="ap@customer.example.com",
            **extra):
    body = {"number": number, "customer_name": f"Customer {number}", "customer_email": email, "currency": "USD",
            "issue_date": min(d(-90), due), "due_date": due,
            "lines": [{"description": a, "quantity": q, "unit_price": p} for a, q, p in lines], **extra}
    r = actor.post("/api/v1/business/invoices", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def active(actor, key="finance", edit=None):
    """Hire → generate (→ edit) → approve → pass the readiness suite → activate (observation stage)."""
    inst, cfg = approved(actor, key, edit)
    assert run(actor, inst)["passed"] is True
    r = actor.post(f"/api/v1/agents/{inst['id']}/activate", json={"config_hash": cfg["config_hash"]})
    assert r.status_code == 200, r.text
    return inst, cfg


def start(actor, inst, task_key=None, request=None, **headers):
    r = actor.client.post("/api/v1/workflows", json={"agent_id": inst["id"], "task_key": task_key,
                                                     "request": request}, headers={**actor.h(), **headers})
    assert r.status_code == 202, r.text
    return actor.get(f"/api/v1/workflows/{r.json()['id']}").json()


def steps(detail, tool):
    return [x for x in detail["executions"] if x["tool"] == tool]


def customer_mail(db):
    return db.scalars(select(EmailOutbox).where(EmailOutbox.to_email.like("%@customer.example.com"))).all()


def any_time(body):
    body["config"]["operating"]["execution_window"] = "any_time"


# ---- registry ----------------------------------------------------------------------------------------------------

def test_registry_describes_every_tool_and_has_no_escape_hatch(owner):
    reg = owner.get("/api/v1/tools").json()
    assert reg["version"] == registry.REGISTRY_VERSION
    tools = {t["key"]: t for t in reg["tools"]}
    for t in tools.values():
        for field in ("description", "input_schema", "output_schema", "scope", "risk", "validation", "approval",
                      "timeout_seconds", "retry", "audit", "idempotency"):
            assert field in t, (t["key"], field)
        assert t["timeout_seconds"] > 0 and t["retry"]["max_attempts"] >= 1
    assert {"invoices.read", "expenses.read", "reminder.draft", "reminder.send", "knowledge.search", "escalate",
            "reports.read", "kpi.read", "briefing.draft", "agents.delegate"} <= {k for k, t in tools.items()
                                                                                if t["available"]}
    assert tools["reminder.send"]["approval"] == "always" and tools["reminder.send"]["retry"]["max_attempts"] == 1
    assert tools["crm.read"]["available"] is False and "not connected" in tools["crm.read"]["unavailable_reason"]
    assert not any(w in k for k in tools for w in ("sql", "shell", "http", "exec", "payment", "refund"))
    assert tools["invoices.read"]["input_schema"]["additionalProperties"] is False


# ---- business records --------------------------------------------------------------------------------------------

def test_business_records_use_validated_calculations(owner, rival, app_db):
    setup_company(owner)
    inv = invoice(owner, "INV-1", due=d(-10), lines=(("Paper", "3", "1250.00"), ("Toner", "0.5", "0.01")))
    assert inv["total"] == "3750.01" and inv["balance"] == "3750.01"  # 0.5 × 0.01 = 0.005 → 0.01 (half-up)
    assert inv["state"] == "overdue" and inv["days_overdue"] == 10 and inv["checks"] == []
    pay = lambda amount, ref=None: owner.post(f"/api/v1/business/invoices/{inv['id']}/payments",  # noqa: E731
                                              json={"amount": amount, "received_on": d(0), "reference": ref})
    assert pay("5000.00").json()["error"]["code"] == "overpayment"
    assert pay("750.01", "BANK-1").status_code == 201
    assert pay("1.00", "BANK-1").status_code == 409  # same bank reference twice
    after = owner.get(f"/api/v1/business/invoices/{inv['id']}").json()
    assert (after["paid"], after["balance"], after["state"]) == ("750.01", "3000.00", "overdue")
    assert owner.post(f"/api/v1/business/invoices/{inv['id']}/void", json={"reason": "x"}).status_code == 409
    imported = invoice(owner, "INV-2", due=d(5), lines=(("A", "1", "10000.00"), ("B", "1", "2000.00")),
                       recorded_total="12500.00", source="import")
    assert imported["checks"] == ["Invoice INV-2: lines add up to 12000.00 but the total is 12500.00"]
    assert owner.post("/api/v1/business/invoices", json={**{k: imported[k] for k in (
        "number", "customer_name", "currency", "issue_date", "due_date")}, "lines": [
        {"description": "x", "unit_price": "1"}]}).status_code == 409  # duplicate number
    rec = owner.get("/api/v1/business/receivables").json()
    assert rec["outstanding_by_currency"] == {"USD": "15000.00"} and rec["overdue_by_currency"] == {"USD": "3000.00"}
    assert rival.get(f"/api/v1/business/invoices/{inv['id']}").status_code == 404
    assert rival.get("/api/v1/business/invoices").json() == []
    member = join(owner, "member@acme.example.com", "member")
    assert member.get("/api/v1/business/invoices").status_code == 403  # financial records need records.read
    set_tenant(app_db, uuid.UUID(owner.org_id))
    for table in ("payments", "invoice_lines"):  # corrections are new records, never edits
        with pytest.raises(ProgrammingError, match="permission denied"):
            app_db.execute(text(f"UPDATE {table} SET amount = 0"))  # noqa: S608
        app_db.rollback()
        set_tenant(app_db, uuid.UUID(owner.org_id))


# ---- the MVP slice: an authorised read-only finance task with tool evidence --------------------------------------

def test_invoice_review_runs_with_evidence_drafts_and_escalation(owner, db, app_db):
    setup_company(owner)
    overdue = invoice(owner, "INV-100", due=d(-40), lines=(("Consulting", "2", "2500.00"),))
    invoice(owner, "INV-101", due=d(14))
    wrong = invoice(owner, "INV-102", due=d(-5), lines=(("A", "1", "10000.00"), ("B", "1", "2000.00")),
                    recorded_total="12500.00", source="import")
    paid = invoice(owner, "INV-103", due=d(-3))
    owner.post(f"/api/v1/business/invoices/{paid['id']}/payments", json={"amount": "1000.00", "received_on": d(0)})
    inst, cfg = active(owner)
    detail = start(owner, inst, "review-outstanding-invoices")
    assert detail["status"] == "completed", (detail["status_reason"], detail["validation"])
    assert detail["config_hash"] == cfg["config_hash"] and detail["trigger_type"] == "on_demand"
    assert detail["planner"]["mode"] == "playbook" and "no AI model planned" in detail["planner"]["label"]
    assert all(c["ok"] for c in detail["validation"]["checks"]), detail["validation"]
    read = steps(detail, "invoices.read")[0]
    assert read["status"] == "succeeded" and read["scope"] == "data.read" and read["decision"] == "executed"
    assert {e["label"] for e in read["evidence"]} == {"Invoice INV-100", "Invoice INV-101", "Invoice INV-102"}
    # INV-102's balance uses the total of its lines (12000.00), not the imported figure it disagrees with.
    assert read["output"]["outstanding_by_currency"] == {"USD": "18000.00"}
    draft = steps(detail, "reminder.draft")
    assert [x["input"]["invoice_id"] for x in draft] == [overdue["id"]]  # only the clean overdue invoice
    esc = steps(detail, "escalate")[0]
    assert esc["input"]["subject"] == "invoice:INV-102" and esc["status"] == "succeeded"
    assert "Outstanding: 18000.00 USD" in detail["output"]["summary"]
    finding = next(f for f in detail["output"]["findings"] if f["invoice"] == "INV-100")
    assert (finding["priority"], finding["action"], finding["days_overdue"]) == ("medium", "reminder drafted", 40)
    assert next(f for f in detail["output"]["findings"] if f["invoice"] == wrong["number"])["action"] == "escalated"
    drafts = owner.get("/api/v1/business/drafts").json()
    assert len(drafts) == 1 and drafts[0]["status"] == "draft" and "5000.00 USD" in drafts[0]["body"]
    assert not customer_mail(db)  # drafting sends nothing
    # A second run reuses the open draft instead of duplicating it.
    again = start(owner, inst, "review-outstanding-invoices")
    assert steps(again, "reminder.draft")[0]["output"]["reused_existing"] is True
    assert len(owner.get("/api/v1/business/drafts").json()) == 1
    # The evidence ledger is write-once for the app role.
    set_tenant(app_db, uuid.UUID(owner.org_id))
    with pytest.raises(DBAPIError, match="write-once"):
        app_db.execute(text("UPDATE tool_executions SET status = 'failed'"))
    app_db.rollback()
    set_tenant(app_db, uuid.UUID(owner.org_id))
    with pytest.raises(ProgrammingError, match="permission denied"):
        app_db.execute(text("DELETE FROM tool_executions"))
    app_db.rollback()
    set_tenant(app_db, uuid.UUID(owner.org_id))
    with pytest.raises(ProgrammingError, match="permission denied"):
        app_db.execute(text("DELETE FROM workflow_runs"))
    app_db.rollback()
    ledger = owner.get(f"/api/v1/tools/executions?run_id={detail['id']}").json()
    assert [x["id"] for x in ledger] == [x["id"] for x in detail["executions"]]


def test_requests_are_idempotent_and_guarded(owner, monkeypatch, db, app_db):
    setup_company(owner)
    inst, _ = active(owner)
    a = start(owner, inst, request="Which invoices are overdue?", **{"Idempotency-Key": "k-1"})
    b = start(owner, inst, request="Which invoices are overdue?", **{"Idempotency-Key": "k-1"})
    assert a["id"] == b["id"] and a["status"] == "completed"
    assert owner.post("/api/v1/workflows", json={"agent_id": inst["id"], "task_key": "nope"}).status_code == 404
    viewer = join(owner, "viewer@acme.example.com", "viewer")
    assert viewer.post("/api/v1/workflows", json={"agent_id": inst["id"], "request": "x"}).status_code == 403
    assert viewer.get("/api/v1/workflows").status_code == 200  # task.read: the list, not the evidence
    assert viewer.get(f"/api/v1/workflows/{a['id']}").status_code == 403
    # Paused: nothing starts.
    owner.post(f"/api/v1/agents/{inst['id']}/pause", json={"reason": "freeze"})
    r = owner.post("/api/v1/workflows", json={"agent_id": inst["id"], "request": "x"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "not_allowed"
    # A queued run whose configuration is changed behind the API is blocked when it is claimed.
    owner.post(f"/api/v1/agents/{inst['id']}/resume", json={"config_hash": a["config_hash"]})
    monkeypatch.setattr(jobs, "dispatch", lambda job_id: None)
    queued = owner.post("/api/v1/workflows", json={"agent_id": inst["id"], "request": "later"}).json()
    assert queued["status"] == "queued"
    db.execute(text("UPDATE task_definitions SET title = 'tampered' WHERE instance_id = :i"), {"i": inst["id"]})
    db.commit()
    set_tenant(app_db, uuid.UUID(owner.org_id))
    orchestration.advance(app_db, uuid.UUID(queued["id"]))
    blocked = owner.get(f"/api/v1/workflows/{queued['id']}").json()
    assert blocked["status"] == "blocked" and "changed after it was approved" in blocked["status_reason"]


# ---- approvals bound to the exact action ---------------------------------------------------------------------------

def can_send(body):
    body["config"]["permissions"]["comms.external"] = "approval_required"
    body["config"]["job"]["authorized_tools"].append("reminder.send")
    for t in body["tasks"]:
        if t["key"] == "review-outstanding-invoices":
            t["required_permissions"].append("comms.external")
            t["approval_required"], t["approval_reason"] = True, "Sending reminders needs approval."


def test_held_send_needs_approval_of_its_exact_parameters(owner, db):
    setup_company(owner)
    inv = invoice(owner, "INV-200", due=d(-70), lines=(("Audit", "1", "8000.00"),))
    inst, _ = active(owner, edit=can_send)
    detail = start(owner, inst, "review-outstanding-invoices")
    assert detail["status"] == "awaiting_approval"
    held = steps(detail, "reminder.send")[0]
    assert held["status"] == "held" and "Observation stage" in held["reason"]
    pending = owner.get("/api/v1/approvals/actions").json()
    assert len(pending) == 1
    req = pending[0]
    assert req["parameters"]["recipient"] == "ap@customer.example.com" and "8000.00 USD" in req["parameters"]["body"]
    assert req["tool"] == "reminder.send" and req["risk"] == "high"
    url = f"/api/v1/approvals/actions/{req['id']}/decide"
    assert owner.post(url, json={"decision": "approved", "params_hash": "0" * 64}).json()["error"]["code"] == \
        "action_changed"
    manager = join(owner, "manager@acme.example.com", "manager")
    assert manager.post(url, json={"decision": "approved", "params_hash": req["params_hash"]}).status_code == 403
    # The policy changes while the request waits: the approval no longer matches, a new one is raised.
    r = owner.post("/api/v1/rules", json={"title": "Reminder cap", "statement": "At most one reminder a week.",
                                          "applies_to": ["finance"]})
    assert r.status_code == 201, r.text
    decided = owner.post(url, json={"decision": "approved", "params_hash": req["params_hash"]}).json()
    assert decided["status"] == "superseded"
    detail = owner.get(f"/api/v1/workflows/{detail['id']}").json()
    assert detail["status"] == "awaiting_approval"
    assert "changed after it was approved" in steps(detail, "reminder.send")[-1]["reason"]
    assert not customer_mail(db)
    req2 = owner.get("/api/v1/approvals/actions").json()[0]
    assert req2["id"] != req["id"] and req2["params_hash"] != req["params_hash"]
    r = owner.post(f"/api/v1/approvals/actions/{req2['id']}/decide",
                   json={"decision": "approved", "params_hash": req2["params_hash"], "note": "OK to send"})
    assert r.json()["status"] == "used"
    detail = owner.get(f"/api/v1/workflows/{detail['id']}").json()
    assert detail["status"] == "completed", detail["validation"]
    sent = steps(detail, "reminder.send")[-1]
    assert sent["status"] == "succeeded" and sent["approval_request_id"] == req2["id"]
    assert sent["output"]["delivery"]["label"].startswith("Development outbox")
    mail = customer_mail(db)
    assert len(mail) == 1 and mail[0].to_email == "ap@customer.example.com" and inv["number"] in mail[0].subject
    kinds = owner.get("/api/v1/approvals").json()
    assert {"tool_action"} <= {a["subject_type"] for a in kinds}
    # A rejected send is recorded as rejected, nothing is sent.
    invoice(owner, "INV-201", due=d(-50), email="other@customer.example.com")
    second = start(owner, inst, "review-outstanding-invoices")
    req3 = owner.get("/api/v1/approvals/actions").json()[0]
    assert owner.post(f"/api/v1/approvals/actions/{req3['id']}/decide",
                      json={"decision": "rejected", "params_hash": req3["params_hash"]}).status_code == 422
    owner.post(f"/api/v1/approvals/actions/{req3['id']}/decide",
               json={"decision": "rejected", "params_hash": req3["params_hash"], "note": "Customer called us"})
    second = owner.get(f"/api/v1/workflows/{second['id']}").json()
    assert second["status"] == "completed", second["validation"]
    assert [x["status"] for x in steps(second, "reminder.send")] == ["held", "rejected"]
    reminded = next(f for f in second["output"]["findings"] if f["invoice"] == "INV-200")
    assert reminded["action"].startswith("reminded on ")  # one reminder a week: not drafted again
    assert len(customer_mail(db)) == 1


# ---- events, schedules ---------------------------------------------------------------------------------------------

def overdue_task(body):
    any_time(body)
    body["tasks"].append({
        "key": "overdue-watch", "title": "Watch overdue invoices", "description": "", "inputs": [], "actions": [],
        "expected_output": "", "completion_criteria": [], "priority": "normal", "sla_minutes": None,
        "policy_refs": [], "required_permissions": ["data.read"], "approval_required": False,
        "approval_reason": None, "failure": {"max_retries": 2, "retry_backoff_minutes": 15, "on_failure": "escalate"},
        "depends_on": [], "trigger": {"type": "event", "event": "invoice.overdue", "schedule": None}})


def test_events_and_schedules_start_each_run_once(owner):
    setup_company(owner)
    inst, _ = active(owner, edit=overdue_task)
    e = owner.post("/api/v1/business/expenses", json={"incurred_on": d(0), "supplier": "Grab", "description":
                                                      "Taxi fare to client", "amount": "350.00", "currency": "USD"})
    assert e.status_code == 201
    runs = owner.get(f"/api/v1/workflows?agent_id={inst['id']}").json()
    exp = next(r for r in runs if r["task_key"] == "expense-categorisation")
    assert exp["trigger"]["subject_id"] == e.json()["id"] and exp["status"] == "completed"
    detail = owner.get(f"/api/v1/workflows/{exp['id']}").json()
    assert "rule-based suggestion \"travel\"" in detail["output"]["summary"]
    assert "No confirmed limit for this currency" in detail["output"]["summary"]
    # invoice.overdue: once per invoice, however often the scheduler ticks.
    invoice(owner, "INV-300", due=d(-2))
    first, second = scheduler.tick(), scheduler.tick()
    assert first["overdue_events"] == 1 and second["overdue_events"] == 0
    # Scheduled task: the 16:00 Manila weekday review becomes exactly one run per occurrence.
    monday = datetime(2026, 10, 12, 8, 5, tzinfo=UTC)  # 16:05 in Manila
    assert scheduler.tick(monday)["scheduled"] == 1
    assert scheduler.tick(monday + timedelta(minutes=1))["scheduled"] == 0
    assert scheduler.tick(monday + timedelta(hours=3))["scheduled"] == 0  # outside the look-back window
    keys = [r["trigger"].get("occurrence") for r in owner.get(f"/api/v1/workflows?agent_id={inst['id']}").json()
            if r["trigger_type"] == "schedule"]
    assert keys == ["2026-10-12T08:00:00+00:00"]


# ---- retries, unknown outcomes, model output ----------------------------------------------------------------------

def test_transient_faults_retry_and_unknown_outcomes_are_not_success(owner, monkeypatch, db, app_db):
    setup_company(owner)
    inst, _ = active(owner)
    calls = {"n": 0}
    real = registry._IMPLEMENTED["invoices.read"]

    def flaky(ctx, data):
        calls["n"] += 1
        if calls["n"] == 1:
            raise handlers.Transient("connection reset")
        return real.handler(ctx, data)

    monkeypatch.setitem(registry._IMPLEMENTED, "invoices.read", dataclasses.replace(real, handler=flaky))
    detail = start(owner, inst, "review-outstanding-invoices")
    read = steps(detail, "invoices.read")[0]
    assert (read["status"], read["attempts"]) == ("succeeded", 2) and detail["status"] == "completed"

    calls["effect"] = 0

    def lost(ctx, data):
        calls["effect"] += 1
        raise handlers.Transient("gateway timeout")

    effect = registry.ToolDef("test.effect", "Notify an external system", "test", "records.draft",
                              registry.KpiReadIn, {}, lost, platform=True, idempotent=False, transactional=False,
                              max_attempts=1)
    original = registry.tools_for
    monkeypatch.setattr(registry, "tools_for", lambda spec: {**original(spec), "test.effect": effect})

    def plan(ctx):
        return planner.call("test.effect", {}) if not ctx.last("test.effect") else planner.finish("Notified.")

    monkeypatch.setitem(planner.PLAYBOOKS, ("finance", "request"), plan)
    detail = start(owner, inst, request="notify")
    row = steps(detail, "test.effect")[0]
    assert row["status"] == "unverified" and "outcome is unknown" in row["reason"] and row["finished_at"]
    assert calls["effect"] == 1 and row["attempts"] == 1  # a non-idempotent effect is never retried
    assert detail["status"] == "unverified"
    assert not next(c for c in detail["validation"]["checks"] if c["label"] == "Every outcome is known")["ok"]
    # A worker that died mid-call leaves a `started` row; the retried job marks it unverified and doesn't repeat it.
    monkeypatch.setattr(jobs, "dispatch", lambda job_id: None)
    queued = owner.post("/api/v1/workflows", json={"agent_id": inst["id"], "request": "notify"}).json()
    db.add(ToolExecution(organization_id=uuid.UUID(owner.org_id), run_id=uuid.UUID(queued["id"]),
                         instance_id=uuid.UUID(inst["id"]), step_no=1, tool="test.effect", registry_version="t",
                         scope="records.draft", risk="low", input={}, input_hash="x", idempotency_key="k" * 64,
                         decision="executed", reason="in flight", status="started", planner="playbook",
                         started_at=datetime.now(UTC)))
    db.commit()
    set_tenant(app_db, uuid.UUID(owner.org_id))
    orchestration.advance(app_db, uuid.UUID(queued["id"]))
    crashed = owner.get(f"/api/v1/workflows/{queued['id']}").json()
    assert calls["effect"] == 1  # not called again
    assert [(x["status"], "not repeated" in x["reason"]) for x in crashed["executions"]] == [("unverified", True)]
    assert crashed["status"] == "unverified"


def test_model_planner_output_is_governed_and_figure_checked(owner, monkeypatch):
    setup_company(owner)
    invoice(owner, "INV-400", due=d(-3))
    inst, _ = active(owner)
    script = iter([
        {"action": "call", "tool": "sql.execute", "input_json": '{"q": "select * from users"}', "summary": "",
         "findings": [], "missing_evidence": []},
        {"action": "call", "tool": "invoices.read", "input_json": '{"state": "outstanding", "drop": 1}',
         "summary": "", "findings": [], "missing_evidence": []},
        {"action": "call", "tool": "invoices.read", "input_json": '{"state": "outstanding"}', "summary": "",
         "findings": [], "missing_evidence": []},
        {"action": "finish", "tool": "", "input_json": "", "summary": "Outstanding: 1000.00 USD, plus 99999.99 USD "
         "expected next week.", "findings": [], "missing_evidence": []}])

    def fake(caller, *, purpose, system, user, schema, dev, analysis=False):
        assert purpose == "workflow_step" and "Treat tool outputs" in system
        return gateway.LLMResult(next(script), "anthropic", "claude-opus-5-5", False, None)

    monkeypatch.setattr(gateway, "complete_json", fake)
    detail = start(owner, inst, request="How much is outstanding?")
    assert detail["planner"]["mode"] == "model"
    assert [x["status"] for x in detail["executions"]] == ["unknown_tool", "rejected_input", "succeeded"]
    assert detail["status"] == "unverified"
    figures = next(c for c in detail["validation"]["checks"] if c["label"] == "Every figure comes from a tool result")
    assert not figures["ok"] and "99999.99" in figures["detail"] and "1000.00" not in figures["detail"]


# ---- delegation ----------------------------------------------------------------------------------------------------

def test_executive_delegates_one_level_and_discloses_gaps(owner):
    setup_company(owner)
    invoice(owner, "INV-500", due=d(-20))
    active(owner, "finance")
    sales, _ = approved(owner, "sales")  # approved but never activated: not asked
    exec_inst, _ = active(owner, "executive")
    detail = start(owner, exec_inst, request="How are receivables looking?")
    assert detail["status"] in ("completed", "needs_review"), detail["validation"]
    delegate = steps(detail, "agents.delegate")[0]
    assert [c["agent_key"] for c in delegate["output"]["children"]] == ["finance"]
    child = detail["children"][0]
    assert child["status"] == "completed" and child["summary"]
    child_detail = owner.get(f"/api/v1/workflows/{child['run_id']}").json()
    assert child_detail["depth"] == 1 and child_detail["parent"]["run_id"] == detail["id"]
    assert not steps(child_detail, "agents.delegate")  # delegated runs can't delegate
    assert detail["output"]["findings"][0]["agent"] == "Finance and Accounting Agent"
    assert sales["id"] not in str(detail)
    top = owner.get("/api/v1/workflows?top_level=true").json()
    assert child["run_id"] not in {r["id"] for r in top}


# ---- tenancy -------------------------------------------------------------------------------------------------------

def test_runs_evidence_and_requests_are_tenant_isolated(owner, rival, app_db, monkeypatch):
    setup_company(owner)
    invoice(owner, "INV-600", due=d(-70))
    inst, _ = active(owner, edit=can_send)
    detail = start(owner, inst, "review-outstanding-invoices")
    req = owner.get("/api/v1/approvals/actions").json()[0]
    assert rival.get(f"/api/v1/workflows/{detail['id']}").status_code == 404
    assert rival.get("/api/v1/workflows").json() == []
    assert rival.get(f"/api/v1/tools/executions?run_id={detail['id']}").json() == []
    assert rival.get("/api/v1/approvals/actions").json() == []
    assert rival.post(f"/api/v1/approvals/actions/{req['id']}/decide",
                      json={"decision": "approved", "params_hash": req["params_hash"]}).status_code == 404
    assert rival.post("/api/v1/workflows", json={"agent_id": inst["id"], "request": "x"}).status_code == 404
    set_tenant(app_db, uuid.UUID(rival.org_id))
    assert app_db.scalars(select(ToolExecution)).all() == []
    assert app_db.scalars(select(WorkflowRun)).all() == []


def test_daily_limit_and_business_hours_deferral(owner, db):
    setup_company(owner)
    inst, _ = active(owner, edit=lambda body: body["config"]["limits"].__setitem__("max_runs_per_day", 1))
    assert start(owner, inst, request="first")["status"] == "completed"
    second = start(owner, inst, request="second")
    assert second["status"] == "skipped" and "Daily run limit reached (1 runs)" in second["status_reason"]
    # A run deferred to the next opening waits without a job; the scheduler releases it once the time has come.
    row = db.get(WorkflowRun, uuid.UUID(second["id"]))
    later = WorkflowRun(**{c: getattr(row, c) for c in ("organization_id", "instance_id", "configuration_id",
                                                        "config_version", "config_hash", "policy_version",
                                                        "task_key", "task_title", "lock_key")},
                        trigger_type="event", trigger={}, request="deferred", idempotency_key="deferred-1",
                        status="queued", not_before=datetime.now(UTC) + timedelta(hours=1))
    db.add(later)
    db.commit()
    assert scheduler.tick()["released"] == 0
    later.not_before = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()
    assert scheduler.tick()["released"] == 1
    db.refresh(later)
    assert later.status == "skipped"  # it ran the claim: today's limit is still used up
