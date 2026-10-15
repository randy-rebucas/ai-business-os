"""Creating workflow runs — shared by on-demand requests, business events and the scheduler.

Creation is idempotent: a second request with the same idempotency key returns None instead of a second run (the
unique constraint decides under concurrency). A run deferred to business hours gets its job when the scheduler sees
`not_before` pass; every other run is queued for the worker as soon as the creating transaction commits.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from abos.agents.models import AgentConfiguration, AgentInstance
from abos.governance import rules as rules_service
from abos.jobs import service as jobs
from abos.orchestration.models import WorkflowRun

JOB_KIND = "workflow_run"


def new_run(db: Session, inst: AgentInstance, *, task_key: str, task_title: str, trigger_type: str,
            trigger: dict[str, Any], idempotency_key: str, lock_key: str | None = None, request: str | None = None,
            requested_by_id: uuid.UUID | None = None, parent: WorkflowRun | None = None,
            not_before: datetime | None = None) -> WorkflowRun | None:
    cfg = db.get(AgentConfiguration, inst.approved_config_id) if inst.approved_config_id else None
    if cfg is None:
        return None
    if db.scalar(select(WorkflowRun.id).where(WorkflowRun.organization_id == inst.organization_id,
                                              WorkflowRun.idempotency_key == idempotency_key)):
        return None
    run = WorkflowRun(id=uuid.uuid4(), organization_id=inst.organization_id, instance_id=inst.id,
                      configuration_id=cfg.id, config_version=cfg.version, config_hash=cfg.config_hash,
                      policy_version=rules_service.policy_version(db, inst.organization_id), task_key=task_key,
                      task_title=task_title[:200], trigger_type=trigger_type, trigger=trigger, request=request,
                      idempotency_key=idempotency_key[:200], lock_key=(lock_key or f"{inst.id}:{task_key}")[:200],
                      parent_id=parent.id if parent else None, depth=(parent.depth + 1) if parent else 0,
                      status="queued", requested_by_id=requested_by_id, not_before=not_before)
    try:
        with db.begin_nested():
            db.add(run)
            db.flush()
    except IntegrityError:
        return None  # created concurrently under the same key
    if not_before is None or not_before <= datetime.now(UTC):
        jobs.enqueue(db, inst.organization_id, JOB_KIND, run.id)
    return run


def requeue(db: Session, run: WorkflowRun) -> None:
    jobs.enqueue(db, run.organization_id, JOB_KIND, run.id)
