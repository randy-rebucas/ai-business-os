import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import event, select
from sqlalchemy.orm import Session

from abos.core.config import get_settings
from abos.core.db import SessionLocal
from abos.core.errors import report_exception
from abos.core.logging import log_context
from abos.core.tenancy import set_tenant, system_scope
from abos.knowledge.models import JobRun

log = logging.getLogger("abos.jobs")

_PENDING = "abos.jobs_pending"
HANDLERS: dict[str, Callable[[Session, JobRun], None]] = {}


class JobFailed(Exception):
    """Permanent failure: no retry (bad input). Other exceptions are retried up to max_attempts."""


def handler(kind: str):
    def register(fn: Callable[[Session, JobRun], None]):
        HANDLERS[kind] = fn
        return fn

    return register


def _now() -> datetime:
    return datetime.now(UTC)


def enqueue(db: Session, org_id: uuid.UUID, kind: str, target_id: uuid.UUID) -> JobRun:
    job = JobRun(id=uuid.uuid4(), organization_id=org_id, kind=kind, target_id=target_id, status="queued",
                 max_attempts=get_settings().job_max_attempts, steps=[])
    db.add(job)
    db.info.setdefault(_PENDING, []).append(job.id)
    return job


@event.listens_for(Session, "after_commit")
def _dispatch_after_commit(session: Session) -> None:
    if session.in_nested_transaction():
        return  # SQLAlchemy also fires after_commit on SAVEPOINT release; the rows aren't committed yet
    ids = session.info.pop(_PENDING, None)
    for job_id in ids or []:
        dispatch(job_id)


@event.listens_for(Session, "after_rollback")
def _forget_on_rollback(session: Session) -> None:
    if session.in_nested_transaction():
        return  # a savepoint rollback; a job whose row it removed is skipped harmlessly by run_job
    session.info.pop(_PENDING, None)


def dispatch(job_id: uuid.UUID) -> None:
    if get_settings().jobs_eager:
        run_job(job_id)
        return
    from abos.jobs.worker import run_job_task  # noqa: PLC0415 — avoids importing Celery in the API hot path

    try:
        run_job_task.delay(str(job_id))
    except Exception as exc:  # noqa: BLE001 — broker down: the sweeper re-sends queued jobs later
        log.warning("job_dispatch_failed", extra={"fields": {"job_id": str(job_id), "error": type(exc).__name__}})


def step(db: Session, job: JobRun, name: str, **detail) -> None:
    """Append a progress step and heartbeat, committed immediately so the UI can show live progress."""
    job.steps = [*job.steps, {"step": name, "at": _now().isoformat(), **detail}]
    job.heartbeat_at = _now()
    db.commit()


def run_job(job_id: uuid.UUID) -> str:
    """Claim and run one job. Returns the final status (or 'skipped' if another worker has it / it's done)."""
    with SessionLocal() as db:
        with system_scope(db):  # the worker doesn't know the tenant until it reads the row
            job = db.scalar(select(JobRun).where(JobRun.id == job_id).with_for_update(skip_locked=True))
            if job is None or job.status not in ("queued",):
                db.rollback()
                return "skipped"
            org_id = job.organization_id
        set_tenant(db, org_id)
        job.status, job.attempts = "running", job.attempts + 1
        job.started_at = job.heartbeat_at = _now()
        db.commit()
        # Every log line of the handler carries the job and its target (the run/document/delivery id).
        with log_context(job_id=job_id, job_kind=job.kind, org_id=org_id, target_id=job.target_id):
            return _run(db, job_id, job)


def _run(db: Session, job_id: uuid.UUID, job: JobRun) -> str:
    fn = HANDLERS.get(job.kind)
    try:
        if fn is None:
            raise JobFailed(f"No handler for job kind {job.kind!r}")
        fn(db, job)
    except Exception as exc:  # noqa: BLE001 — the job boundary records every failure
        db.rollback()
        job = db.get(JobRun, job_id)
        permanent = isinstance(exc, JobFailed) or job.attempts >= job.max_attempts
        job.status = "failed" if permanent else "queued"
        job.last_error = f"{type(exc).__name__}: {exc}"[:500]
        job.finished_at = _now() if permanent else None
        db.commit()
        log.warning("job_failed", extra={"fields": {"permanent": permanent, "error": type(exc).__name__}})
        if not isinstance(exc, JobFailed):  # JobFailed = bad input, an expected outcome; anything else is a bug
            report_exception(exc, {"attempt": job.attempts, "permanent": permanent}, where="job")
        if not permanent:
            dispatch(job_id)
        return job.status
    job.status, job.finished_at, job.heartbeat_at = "succeeded", _now(), _now()
    db.commit()
    return "succeeded"


def sweep() -> dict[str, int]:
    """Recover jobs whose Redis message was lost or whose worker died (ADR-008)."""
    s = get_settings()
    stale = _now() - timedelta(seconds=s.job_timeout_seconds)
    result = {"redispatched": 0, "requeued": 0, "failed": 0}
    with SessionLocal() as db, system_scope(db):
        for job in db.scalars(select(JobRun).where(JobRun.status == "running", JobRun.heartbeat_at < stale)
                              .with_for_update(skip_locked=True)):
            if job.attempts >= job.max_attempts:
                job.status, job.finished_at, job.last_error = "failed", _now(), "Timed out (no heartbeat)"
                result["failed"] += 1
                _mark_target_failed(db, job)
            else:
                job.status, job.last_error = "queued", "Worker stopped responding; retrying"
                result["requeued"] += 1
        db.commit()
        queued = list(db.scalars(select(JobRun.id).where(JobRun.status == "queued", JobRun.updated_at < stale)))
    for job_id in queued:
        dispatch(job_id)
        result["redispatched"] += 1
    return result


def _mark_target_failed(db: Session, job: JobRun) -> None:
    if job.kind == "ingest_document":
        from abos.knowledge.models import Document  # noqa: PLC0415

        doc = db.get(Document, job.target_id)
        if doc is not None and doc.status in ("queued", "processing"):
            doc.status, doc.error_code, doc.error_message = "failed", "timeout", "Processing timed out"
    elif job.kind == "simulation_run":
        from abos.simulation.models import SimulationRun  # noqa: PLC0415

        run = db.get(SimulationRun, job.target_id)
        if run is not None and run.status in ("queued", "running"):
            run.status, run.error = "error", "The run timed out"
    elif job.kind == "workflow_run":
        from abos.orchestration.models import WorkflowRun  # noqa: PLC0415

        wf = db.get(WorkflowRun, job.target_id)
        if wf is not None and wf.status in ("queued", "running"):
            wf.status, wf.error = "failed", "The run timed out (no heartbeat)"
            wf.status_reason, wf.finished_at = wf.error, _now()
