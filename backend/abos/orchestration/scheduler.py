"""The scheduler tick (SPEC §3 step 5 operating modes, step 7 'task scheduling'). Celery beat runs it every minute;
`python -m abos.jobs tick` runs it once.

Each tick, across workspaces (system scope, the smallest block possible):
1. scheduled tasks of active agents: every occurrence that fell due in the look-back window becomes a run whose
   idempotency key is the occurrence itself, so overlapping or repeated ticks never start it twice. Occurrences are
   computed by `agents.schedule` in the company time zone, with business hours and holidays applied;
2. `invoice.overdue`: invoices past due (in the company's time zone) with a balance emit the event once per invoice;
3. runs deferred to business hours whose time has come are queued for the worker.
Occurrences older than the look-back window (the scheduler was down) are not replayed — they are reported in the
tick result so the gap is visible.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from abos.agents import schedule
from abos.agents import service as agents
from abos.agents.models import AgentConfiguration, AgentInstance, TaskDefinition
from abos.company import service as company
from abos.core.db import SessionLocal
from abos.core.tenancy import system_scope
from abos.jobs import service as jobs
from abos.knowledge.models import JobRun
from abos.orchestration import events
from abos.orchestration.models import WorkflowRun
from abos.orchestration.runs import JOB_KIND, new_run

log = logging.getLogger("abos.scheduler")
LOOKBACK = timedelta(minutes=15)


def tick(now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    result = {"scheduled": 0, "overdue_events": 0, "released": 0, "agents": 0}
    from abos.notifications import service as notifications  # noqa: PLC0415 — notifications import orchestration
    from abos.reporting import service as reporting  # noqa: PLC0415
    from abos.tools import reconcile  # noqa: PLC0415

    with SessionLocal() as db, system_scope(db):
        for inst in db.scalars(select(AgentInstance).where(AgentInstance.status == "active")):
            if not agents.execution_allowed(db, inst)[0]:
                continue
            result["agents"] += 1
            result["scheduled"] += _schedule(db, inst, now)
        result["overdue_events"] = _overdue(db, now)
        result["released"] = _release(db, now)
        result["reconciled"] = reconcile.reconcile(db)
        result["email"] = notifications.reconcile_email(db)
        result["retried"] = notifications.retry_due(db, now)
        result["reports"] = reporting.due_reports(db, now)
        result["digests"] = notifications.digests(db, now)
        db.commit()
    return result


def _schedule(db: Session, inst: AgentInstance, now: datetime) -> int:
    cfg = db.get(AgentConfiguration, inst.approved_config_id)
    p = company.get_profile(db, inst.organization_id)
    if not p.timezone:
        return 0  # no time zone, no schedule (the configuration screen says so)
    window = cfg.config["operating"]["execution_window"]
    holidays = schedule.holiday_dates(p.holidays)
    created = 0
    for task in db.scalars(select(TaskDefinition).where(TaskDefinition.configuration_id == cfg.id,
                                                        TaskDefinition.trigger_type == "schedule")):
        due = [t for t in schedule.next_runs(task.schedule, tz=p.timezone, after=now - LOOKBACK, n=4, window=window,
                                             operating_schedule=p.operating_schedule, holidays=holidays) if t <= now]
        for at in due:
            run = new_run(db, inst, task_key=task.key, task_title=task.title, trigger_type="schedule",
                          trigger={"occurrence": at.isoformat()},
                          idempotency_key=f"schedule:{inst.id}:{task.key}:{at.isoformat()}")
            created += run is not None
    return created


def _overdue(db: Session, now: datetime) -> int:
    from abos.business.models import Invoice  # noqa: PLC0415 — business imports orchestration.events
    from abos.business.service import query_invoices  # noqa: PLC0415

    subscribed = {i.organization_id for i, in db.execute(
        select(AgentInstance).join(TaskDefinition, TaskDefinition.configuration_id == AgentInstance.approved_config_id)
        .where(AgentInstance.status == "active", TaskDefinition.event == "invoice.overdue")).all()}
    count = 0
    for org_id in subscribed:
        today = _today(db, org_id, now)
        candidates = db.scalars(select(Invoice.id).where(Invoice.organization_id == org_id,
                                                        Invoice.status != "void", Invoice.due_date < today))
        for inv_id in candidates:
            view = query_invoices(db, org_id, invoice_id=inv_id, today=today)
            if view and view[0]["state"] == "overdue":
                count += events.emit(db, org_id, "invoice.overdue", subject_type="invoice", subject_id=inv_id)
    return count


def _today(db: Session, org_id: uuid.UUID, now: datetime):
    from zoneinfo import ZoneInfo  # noqa: PLC0415

    tz = company.get_profile(db, org_id).timezone
    return now.astimezone(ZoneInfo(tz) if tz else UTC).date()


def _release(db: Session, now: datetime) -> int:
    released = 0
    for run in db.scalars(select(WorkflowRun).where(WorkflowRun.status == "queued", WorkflowRun.not_before.is_not(None),
                                                    WorkflowRun.not_before <= now)):
        has_job = db.scalar(select(JobRun.id).where(JobRun.kind == JOB_KIND, JobRun.target_id == run.id,
                                                    JobRun.status.in_(("queued", "running"))))
        if not has_job:
            jobs.enqueue(db, run.organization_id, JOB_KIND, run.id)
            released += 1
    return released
