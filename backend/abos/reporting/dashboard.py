"""AI Workforce Control Center (SPEC §3 step 8 'CEO dashboard'): real counts from agents, runs, executions, action
requests and the usage ledger — nothing estimated, nothing invented. Filters: agent, department, run status, date
range (company-local days) and task priority. "Overdue" means a run that took — or, still open, has been waiting —
longer than its task's SLA.
"""

import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from abos.agents import schedule
from abos.agents.models import AgentConfiguration, AgentDefinition, AgentInstance, TaskDefinition
from abos.company import service as company
from abos.governance.models import ActionRequest
from abos.llm.models import ModelUsage
from abos.orchestration.models import WorkflowRun
from abos.reporting.service import window, zone_of
from abos.tools.models import ToolExecution

OPEN = ("queued", "running", "awaiting_approval", "waiting_children")
FINISHED = ("completed", "needs_review", "unverified", "failed")


def control_center(db: Session, org_id: uuid.UUID, *, agent_id: uuid.UUID | None = None,
                   department: str | None = None, status: str | None = None, date_from: date | None = None,
                   date_to: date | None = None, priority: str | None = None) -> dict:
    zone = zone_of(db, org_id)
    now = datetime.now(UTC)
    today = now.astimezone(zone).date()
    date_to = date_to or today
    date_from = date_from or date_to - timedelta(days=6)
    start, end = window(zone, date_from)[0], window(zone, date_to)[1]

    insts = list(db.execute(select(AgentInstance, AgentDefinition).join(
        AgentDefinition, AgentDefinition.id == AgentInstance.definition_id)
        .where(AgentInstance.organization_id == org_id).order_by(AgentDefinition.letter)).all())
    departments = sorted({d.department for _, d in insts})
    scoped = [(i, d) for i, d in insts if (not agent_id or i.id == agent_id)
              and (not department or d.department == department)]
    scope_ids = {i.id for i, _ in scoped}
    live = [i for i, _ in scoped if i.status != "retired"]
    by_status: dict[str, int] = {}
    for i in live:
        by_status[i.status] = by_status.get(i.status, 0) + 1

    # runs in range, with the priority and SLA of the task they ran (from the configuration version they used)
    runs = [r for r in db.scalars(select(WorkflowRun).where(WorkflowRun.organization_id == org_id,
                                                            WorkflowRun.created_at >= start,
                                                            WorkflowRun.created_at < end)
                                  .order_by(WorkflowRun.created_at.desc()).limit(5000)) if r.instance_id in scope_ids]
    tasks = {(t.configuration_id, t.key): t for t in db.scalars(select(TaskDefinition).where(
        TaskDefinition.configuration_id.in_({r.configuration_id for r in runs})))} if runs else {}

    def task_of(r: WorkflowRun) -> TaskDefinition | None:
        return tasks.get((r.configuration_id, r.task_key))

    def prio(r: WorkflowRun) -> str:
        t = task_of(r)
        return t.priority if t else "normal"

    runs = [r for r in runs if (not priority or prio(r) == priority) and (not status or r.status == status)]
    run_ids = [r.id for r in runs]

    def overdue(r: WorkflowRun) -> bool:
        t = task_of(r)
        if not t or not t.sla_minutes or r.status in ("cancelled", "skipped", "blocked"):
            return False
        began = r.started_at or r.created_at
        stop = r.finished_at or now
        return (stop - began).total_seconds() > t.sla_minutes * 60

    pending_actions = db.scalar(select(func.count()).select_from(ActionRequest).where(
        ActionRequest.organization_id == org_id, ActionRequest.status == "pending",
        ActionRequest.instance_id.in_(scope_ids))) if scope_ids else 0
    execs = list(db.scalars(select(ToolExecution).where(ToolExecution.run_id.in_(run_ids)))) if run_ids else []
    escalations = [x for x in execs if x.tool == "escalate" and x.status == "succeeded"]
    names = {i.id: i.name for i, _ in insts}
    dept = {i.id: d.department for i, d in insts}

    usage = dict(db.execute(select(ModelUsage.agent_instance_id, func.coalesce(func.sum(ModelUsage.cost_usd), 0))
                            .where(ModelUsage.organization_id == org_id, ModelUsage.created_at >= start,
                                   ModelUsage.created_at < end)
                            .group_by(ModelUsage.agent_instance_id)).all())
    performance = []
    for i, d in scoped:
        mine = [r for r in runs if r.instance_id == i.id]
        fin = [r for r in mine if r.status in FINISHED]
        done = [r for r in mine if r.status == "completed"]
        durations = [(r.finished_at - r.started_at).total_seconds() for r in fin if r.started_at and r.finished_at]
        performance.append({
            "instance_id": str(i.id), "agent": i.name, "department": d.department, "status": i.status,
            "runs": len(mine), "completed": len(done), "failed": sum(1 for r in mine if r.status == "failed"),
            "unverified": sum(1 for r in mine if r.status == "unverified"),
            "needs_review": sum(1 for r in mine if r.status == "needs_review"),
            "completion_rate": round(len(done) / len(fin), 3) if fin else None,
            "avg_duration_seconds": round(sum(durations) / len(durations), 1) if durations else None,
            "overdue": sum(1 for r in mine if overdue(r)),
            "cost_usd": str(round(usage.get(i.id, 0), 4))})

    upcoming = []
    p = company.get_profile(db, org_id)
    if p.timezone:
        for i in live:
            if i.status != "active" or not i.approved_config_id:
                continue
            cfg = db.get(AgentConfiguration, i.approved_config_id)
            for t in db.scalars(select(TaskDefinition).where(TaskDefinition.configuration_id == cfg.id,
                                                             TaskDefinition.trigger_type == "schedule")):
                if priority and t.priority != priority:
                    continue
                for at in schedule.next_runs(t.schedule, tz=p.timezone, after=now, n=2,
                                             window=cfg.config["operating"]["execution_window"],
                                             operating_schedule=p.operating_schedule,
                                             holidays=schedule.holiday_dates(p.holidays)):
                    upcoming.append({"agent": i.name, "instance_id": str(i.id), "task": t.title, "at": at.isoformat(),
                                     "priority": t.priority})
    for r in db.scalars(select(WorkflowRun).where(WorkflowRun.organization_id == org_id,
                                                  WorkflowRun.status == "queued",
                                                  WorkflowRun.not_before.is_not(None))):
        if r.instance_id in scope_ids:
            upcoming.append({"agent": names.get(r.instance_id), "instance_id": str(r.instance_id),
                             "task": r.task_title, "at": r.not_before.isoformat(), "run_id": str(r.id),
                             "priority": prio(r), "deferred": True})
    upcoming.sort(key=lambda u: u["at"])

    def item(r: WorkflowRun) -> dict:
        return {"run_id": str(r.id), "agent": names.get(r.instance_id), "department": dept.get(r.instance_id),
                "task": r.task_title, "status": r.status, "priority": prio(r), "trigger": r.trigger_type,
                "created_at": r.created_at.isoformat(), "overdue": overdue(r)}

    total_cost = sum((v for k, v in usage.items() if k in scope_ids or (k is None and not agent_id and
                                                                         not department)), start=0)
    from abos.simulation import service as simulation  # noqa: PLC0415 — simulation imports reporting's neighbours

    needs_retest = [x for x in simulation.needs_retest(db, org_id) if uuid.UUID(x["instance_id"]) in scope_ids]
    return {
        "filters": {"agent_id": str(agent_id) if agent_id else None, "department": department, "status": status,
                    "date_from": date_from.isoformat(), "date_to": date_to.isoformat(), "priority": priority,
                    "timezone": str(zone)},
        "options": {"agents": [{"id": str(i.id), "name": i.name} for i, _ in insts if i.status != "retired"],
                    "departments": departments},
        "agents": {"total": len(live), "by_status": by_status, "active": by_status.get("active", 0),
                   "paused": by_status.get("paused", 0), "failed": by_status.get("failed", 0)},
        "tasks": {"assigned": len(runs), "completed": sum(1 for r in runs if r.status == "completed"),
                  "in_progress": sum(1 for r in runs if r.status in ("queued", "running", "waiting_children")),
                  "awaiting_approval": sum(1 for r in runs if r.status == "awaiting_approval"),
                  "pending_actions": pending_actions,
                  "overdue": sum(1 for r in runs if overdue(r)),
                  "failed": sum(1 for r in runs if r.status == "failed"),
                  "unverified": sum(1 for r in runs if r.status == "unverified"),
                  "needs_review": sum(1 for r in runs if r.status == "needs_review"),
                  "blocked": sum(1 for r in runs if r.status in ("blocked", "skipped"))},
        "failed_workflows": [item(r) for r in runs if r.status in ("failed", "unverified")][:20],
        "escalations": [{"execution_id": str(x.id), "run_id": str(x.run_id), "agent": names.get(x.instance_id),
                         "severity": x.output.get("severity"), "reason": x.output.get("reason"),
                         "at": x.created_at.isoformat()}
                        for x in sorted(escalations, key=lambda x: x.created_at, reverse=True)
                        if x.output.get("severity") in ("high", "critical")][:20],
        "performance": performance,
        "needs_retest": needs_retest,
        "costs": {"total_usd": str(round(total_cost, 4)),
                  "label": "Estimates from the usage ledger; development adapters cost nothing"},
        "recent": [item(r) for r in runs[:15]],
        "upcoming": upcoming[:15],
        "overdue": [item(r) for r in runs if overdue(r)][:20],
    }
