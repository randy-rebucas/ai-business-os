"""Daily reports built from execution records (SPEC §3 step 8, ADR-029). Deterministic: no model writes them.

For one agent and one company-local day: the runs created that day, the tool executions they made, the action
requests they raised, the reconciliations of unknown outcomes, the usage ledger and the approved schedule. Every item
carries the ids it came from, indexed in `report_evidence`. Attempted vs completed is explicit: an execution that ran
is *attempted*; only `succeeded` (or `unverified` later confirmed by reconciliation) counts as *completed*; an
unknown outcome stays *unverified* — a timeout is never reported as success.
"""

import uuid
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from abos.agents import schedule
from abos.agents import service as agents
from abos.agents.models import AgentConfiguration, AgentDefinition, AgentInstance, TaskDefinition
from abos.company import service as company
from abos.core.errors import AppError, not_found
from abos.governance.models import ActionRequest
from abos.identity.deps import OrgContext
from abos.llm.models import ModelUsage
from abos.notifications import service as notifications
from abos.orchestration.models import WorkflowRun
from abos.reporting.models import DailyReport, ReportEvidence
from abos.tools import reconcile
from abos.tools.models import RAN, ToolExecution

SECTIONS = ("agent", "assigned", "completed", "in_progress", "failed", "blocked", "awaiting_approval", "actions",
            "outcomes", "evidence", "exceptions", "escalations", "upcoming", "kpis", "costs")
ACTIVE = ("queued", "running", "waiting_children")


def zone_of(db: Session, org_id: uuid.UUID) -> ZoneInfo:
    tz = company.get_profile(db, org_id).timezone
    return ZoneInfo(tz) if tz else ZoneInfo("UTC")


def window(zone: ZoneInfo, day: date) -> tuple[datetime, datetime]:
    return (datetime.combine(day, time(0), zone).astimezone(UTC),
            datetime.combine(day + timedelta(days=1), time(0), zone).astimezone(UTC))


def _run_item(r: WorkflowRun) -> dict:
    return {"run_id": str(r.id), "task": r.task_title, "trigger": r.trigger_type, "status": r.status,
            "reason": r.status_reason, "summary": (r.output or {}).get("summary", "")[:500],
            "finished_at": r.finished_at.isoformat() if r.finished_at else None}


def build(db: Session, inst: AgentInstance, day: date, now: datetime | None = None) -> DailyReport:
    now = now or datetime.now(UTC)
    zone = zone_of(db, inst.organization_id)
    start, end = window(zone, day)
    d = db.get(AgentDefinition, inst.definition_id)
    cfg = db.get(AgentConfiguration, inst.approved_config_id) if inst.approved_config_id else None
    runs = list(db.scalars(select(WorkflowRun).where(WorkflowRun.instance_id == inst.id,
                                                     WorkflowRun.created_at >= start, WorkflowRun.created_at < end)
                           .order_by(WorkflowRun.created_at)))
    run_ids = [r.id for r in runs]
    execs = list(db.scalars(select(ToolExecution).where(ToolExecution.run_id.in_(run_ids))
                            .order_by(ToolExecution.created_at))) if run_ids else []
    recon = reconcile.latest(db, [x.id for x in execs if x.status == "unverified"])
    requests = list(db.scalars(select(ActionRequest).where(ActionRequest.run_id.in_(run_ids)))) if run_ids else []
    evidence: list[tuple[str, str, uuid.UUID]] = []

    def cite(section: str, kind: str, ids) -> None:
        evidence.extend((section, kind, i) for i in ids)

    by = {s: [r for r in runs if r.status in s] for s in (("completed",), ACTIVE, ("failed",),
                                                           ("blocked", "skipped", "cancelled"),
                                                           ("awaiting_approval",))}
    completed, in_progress, failed, blocked, awaiting = (by[k] for k in by)
    for section, items in (("completed", completed), ("in_progress", in_progress), ("failed", failed),
                           ("blocked", blocked), ("awaiting_approval", awaiting)):
        cite(section, "workflow_run", [r.id for r in items])

    # actions performed + verified outcomes (attempted vs completed vs unverified)
    ran = [x for x in execs if x.status in RAN]
    per_tool: dict[str, dict[str, int]] = {}
    for x in execs:
        t = per_tool.setdefault(x.tool, {"attempted": 0, "succeeded": 0, "unverified": 0, "failed": 0,
                                         "not_run": 0})
        if x.status in RAN:
            t["attempted"] += 1
            t[x.status] += 1
        else:
            t["not_run"] += 1
    confirmed = [x for x in ran if x.status == "unverified" and recon.get(x.id) and recon[x.id].outcome == "confirmed"]
    late_failed = [x for x in ran if x.status == "unverified" and recon.get(x.id) and recon[x.id].outcome == "failed"]
    still_unknown = [x for x in ran if x.status == "unverified" and x.id not in recon]
    side_effects = [x for x in ran if x.scope not in (None, "data.read")]
    cite("actions", "tool_execution", [x.id for x in side_effects])
    cite("outcomes", "tool_execution", [x.id for x in still_unknown + confirmed + late_failed])
    outcomes = {
        "attempted": len(ran),
        "completed": sum(1 for x in ran if x.status == "succeeded") + len(confirmed),
        "unverified": len(still_unknown),
        "failed": sum(1 for x in ran if x.status == "failed") + len(late_failed),
        "not_run": len(execs) - len(ran),
        "reconciled": [{"execution_id": str(x.id), "tool": x.tool, "outcome": recon[x.id].outcome,
                        "detail": recon[x.id].detail} for x in confirmed + late_failed],
        "unverified_items": [{"execution_id": str(x.id), "run_id": str(x.run_id), "tool": x.tool,
                              "reason": x.reason} for x in still_unknown],
    }

    exceptions = [{"run_id": str(r.id), "task": r.task_title, "status": r.status, "reason": r.status_reason,
                   "failed_checks": [c["label"] for c in (r.validation or {}).get("checks", []) if not c["ok"]]}
                  for r in runs if r.status in ("needs_review", "unverified", "failed")]
    exceptions += [{"execution_id": str(x.id), "run_id": str(x.run_id), "tool": x.tool, "status": x.status,
                    "reason": x.reason} for x in execs if x.status in ("blocked", "refused", "rejected_input",
                                                                         "unknown_tool", "unavailable")]
    cite("exceptions", "workflow_run", [r.id for r in runs if r.status in ("needs_review", "unverified", "failed")])
    escalations = [x for x in execs if x.tool == "escalate" and x.status == "succeeded"]
    cite("escalations", "tool_execution", [x.id for x in escalations])
    pending_requests = [a for a in requests if a.status == "pending"]
    cite("awaiting_approval", "action_request", [a.id for a in pending_requests])

    # upcoming: the next scheduled occurrences after the period (approved configuration, company calendar)
    upcoming = []
    p = company.get_profile(db, inst.organization_id)
    if cfg and p.timezone:
        window_kind = cfg.config["operating"]["execution_window"]
        for t in db.scalars(select(TaskDefinition).where(TaskDefinition.configuration_id == cfg.id,
                                                         TaskDefinition.trigger_type == "schedule")):
            for at in schedule.next_runs(t.schedule, tz=p.timezone, after=max(end, now), n=1, window=window_kind,
                                         operating_schedule=p.operating_schedule,
                                         holidays=schedule.holiday_dates(p.holidays)):
                upcoming.append({"task": t.title, "at": at.isoformat()})
    deferred = db.scalars(select(WorkflowRun).where(WorkflowRun.instance_id == inst.id,
                                                    WorkflowRun.status == "queued",
                                                    WorkflowRun.not_before.is_not(None)))
    upcoming += [{"task": r.task_title, "at": r.not_before.isoformat(), "run_id": str(r.id), "deferred": True}
                 for r in deferred]
    upcoming.sort(key=lambda u: u["at"])

    # KPIs: platform-measured ones from the records; the catalog's business KPIs have no measurement source yet
    finished = [r for r in runs if r.status in ("completed", "needs_review", "unverified", "failed")]
    tasks = {t.key: t for t in agents.task_rows(db, cfg)} if cfg else {}
    sla_runs = [r for r in finished if r.started_at and r.finished_at and r.task_key in tasks
                and tasks[r.task_key].sla_minutes]
    sla_met = [r for r in sla_runs if (r.finished_at - r.started_at).total_seconds() <= 60 *
               tasks[r.task_key].sla_minutes]
    kpis = {"measured": [
        {"name": "Runs completed with every check passed", "value": f"{len(completed)} of {len(finished)}",
         "basis": "workflow runs finished in the period"},
        {"name": "Runs within their SLA", "value": f"{len(sla_met)} of {len(sla_runs)}" if sla_runs else "no SLA runs",
         "basis": "task SLA minutes vs run duration"},
        {"name": "Actions completed vs attempted", "value": f"{outcomes['completed']} of {outcomes['attempted']}",
         "basis": "tool executions that ran"}],
        "defined": [{"name": k["name"], "target": k["target"], "value": None,
                     "note": "No measurement source is connected for this KPI yet."} for k in d.spec["kpis"]]}

    usage = db.execute(select(func.count(), func.coalesce(func.sum(ModelUsage.cost_usd), 0),
                              func.count().filter(ModelUsage.provider.in_(("dev", "hash"))))
                       .where(ModelUsage.agent_instance_id == inst.id, ModelUsage.created_at >= start,
                              ModelUsage.created_at < end)).one()
    costs = {"model_calls": usage[0], "model_cost_usd": str(Decimal(str(usage[1])).quantize(Decimal("0.0001"))),
             "dev_calls": usage[2], "tool_executions": len(execs),
             "label": "Development adapters — no AI model was called, so this cost nothing" if usage[2] else None}

    content = {
        "agent": {"name": inst.name, "definition_key": inst.definition_key, "department": d.department,
                  "date": day.isoformat(), "timezone": str(zone), "period_start": start.isoformat(),
                  "period_end": end.isoformat(), "deployment_stage": inst.deployment_stage},
        "assigned": [{"key": t.key, "title": t.title, "trigger": t.trigger_type,
                      "runs": sum(1 for r in runs if r.task_key == t.key)} for t in tasks.values()]
        + ([{"key": "request", "title": "Requests from people and the Executive agent", "trigger": "on_demand",
             "runs": sum(1 for r in runs if r.task_key == "request")}] if any(r.task_key == "request" for r in runs)
           else []),
        "completed": [_run_item(r) for r in completed],
        "in_progress": [_run_item(r) for r in in_progress],
        "failed": [_run_item(r) for r in failed],
        "blocked": [_run_item(r) for r in blocked],
        "awaiting_approval": [_run_item(r) for r in awaiting]
        + [{"request_id": str(a.id), "run_id": str(a.run_id), "action": a.tool_label, "reason": a.reason,
            "requested_at": a.created_at.isoformat()} for a in pending_requests],
        "actions": {"per_tool": per_tool,
                    "side_effects": [{"execution_id": str(x.id), "run_id": str(x.run_id), "tool": x.tool,
                                      "status": x.status, "evidence": x.evidence[:5]} for x in side_effects]},
        "outcomes": outcomes,
        "evidence": {"runs": len(runs), "tool_executions": len(execs), "action_requests": len(requests),
                     "source_documents": sorted({e["label"] for x in execs for e in (x.evidence or [])
                                                 if e.get("type") == "document_chunk"})},
        "exceptions": exceptions,
        "escalations": [{"execution_id": str(x.id), "run_id": str(x.run_id), "severity": x.output.get("severity"),
                         "reason": x.output.get("reason")} for x in escalations],
        "upcoming": upcoming[:20],
        "kpis": kpis,
        "costs": costs,
    }
    counts = {"runs": len(runs), "completed": len(completed), "in_progress": len(in_progress), "failed": len(failed),
              "blocked": len(blocked), "awaiting_approval": len(awaiting) + len(pending_requests),
              "attempted": outcomes["attempted"], "verified": outcomes["completed"],
              "unverified": outcomes["unverified"], "escalations": len(escalations), "exceptions": len(exceptions)}
    summary = (f"{len(runs)} run(s): {len(completed)} completed, {len(failed)} failed, "
               f"{counts['awaiting_approval']} awaiting approval, {len(in_progress)} in progress. Actions: "
               f"{outcomes['completed']} completed of {outcomes['attempted']} attempted"
               + (f", {outcomes['unverified']} with unknown outcome" if outcomes["unverified"] else "")
               + f". Escalations: {len(escalations)}.") if runs else "No task ran in this period."

    report = db.scalar(select(DailyReport).where(DailyReport.instance_id == inst.id, DailyReport.report_date == day))
    first_final = report is None or not report.final
    if report is None:
        report = DailyReport(organization_id=inst.organization_id, instance_id=inst.id, report_date=day, version=0)
        db.add(report)
    report.timezone, report.period_start, report.period_end = str(zone), start, end
    report.final, report.version, report.generated_at = now >= end, report.version + 1, now
    report.summary, report.counts, report.content = summary[:1000], counts, content
    db.flush()
    for old in db.scalars(select(ReportEvidence).where(ReportEvidence.report_id == report.id)):
        db.delete(old)
    for section, kind, ref in dict.fromkeys(evidence):
        db.add(ReportEvidence(organization_id=inst.organization_id, report_id=report.id, section=section,
                              ref_type=kind, ref_id=ref))
    if report.final and first_final:
        notifications.notify(db, inst.organization_id, kind="report_ready", severity="info",
                             title=f"Daily report: {inst.name}, {day.isoformat()}", body=summary,
                             link=f"/app/reports/{report.id}", subject_type="daily_report", subject_id=report.id,
                             dedupe=f"report:{report.id}")
    return report


def due_reports(db: Session, now: datetime) -> int:
    """Final reports for every activated agent and every finished local day of the last week not yet reported."""
    made = 0
    for inst in db.scalars(select(AgentInstance).where(AgentInstance.deployment_stage.is_not(None),
                                                       AgentInstance.status != "retired",
                                                       AgentInstance.activated_at.is_not(None))):
        zone = zone_of(db, inst.organization_id)
        today = now.astimezone(zone).date()
        done = set(db.scalars(select(DailyReport.report_date).where(DailyReport.instance_id == inst.id,
                                                                    DailyReport.final.is_(True))))
        for back in range(1, 8):
            day = today - timedelta(days=back)
            if day in done or window(zone, day)[1] <= inst.activated_at:
                continue
            build(db, inst, day, now)
            made += 1
    return made


# ---- reading -----------------------------------------------------------------------------------------------------

def get(db: Session, ctx: OrgContext, report_id: uuid.UUID) -> DailyReport:
    r = db.get(DailyReport, report_id)
    if r is None or r.organization_id != ctx.org_id:
        raise not_found("Report")
    return r


def listing(db: Session, ctx: OrgContext, *, instance_id: uuid.UUID | None = None, date_from: date | None = None,
            date_to: date | None = None, limit: int = 100) -> list[tuple[DailyReport, str]]:
    stmt = (select(DailyReport, AgentInstance.name).join(AgentInstance, AgentInstance.id == DailyReport.instance_id)
            .where(DailyReport.organization_id == ctx.org_id))
    if instance_id:
        stmt = stmt.where(DailyReport.instance_id == instance_id)
    if date_from:
        stmt = stmt.where(DailyReport.report_date >= date_from)
    if date_to:
        stmt = stmt.where(DailyReport.report_date <= date_to)
    return [tuple(x) for x in db.execute(stmt.order_by(DailyReport.report_date.desc(), AgentInstance.name)
                                         .limit(limit)).all()]


def generate_now(db: Session, ctx: OrgContext, inst: AgentInstance, day: date | None) -> DailyReport:
    zone = zone_of(db, ctx.org_id)
    today = datetime.now(UTC).astimezone(zone).date()
    day = day or today
    if day > today:
        raise AppError(422, "validation_error", "A report can't cover a future day")
    if inst.deployment_stage is None:
        raise AppError(409, "not_activated", "Reports start once the agent has been activated")
    report = build(db, inst, day)
    db.commit()
    db.refresh(report)
    return report


def evidence_of(db: Session, report: DailyReport) -> list[ReportEvidence]:
    return list(db.scalars(select(ReportEvidence).where(ReportEvidence.report_id == report.id)))
