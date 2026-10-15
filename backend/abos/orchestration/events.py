"""Business events → event-driven tasks (SPEC step 5 'event-driven' operating mode).

`emit` runs inside the transaction that recorded the business change, so a task starts iff the change committed.
Only active agents whose *approved* configuration subscribes to the event get a run, one per event subject (the
idempotency key), deferred to the next opening when the agent's execution window is business hours.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from abos.agents import policy, schedule
from abos.agents.models import AgentConfiguration, AgentInstance, TaskDefinition
from abos.company import service as company
from abos.orchestration.runs import new_run


def emit(db: Session, org_id: uuid.UUID, event: str, *, subject_type: str, subject_id: uuid.UUID,
         **extra) -> int:
    if event not in policy.EVENTS:
        raise ValueError(f"Unknown event {event!r}")
    rows = db.execute(select(TaskDefinition, AgentInstance, AgentConfiguration)
                      .join(AgentInstance, AgentInstance.approved_config_id == TaskDefinition.configuration_id)
                      .join(AgentConfiguration, AgentConfiguration.id == AgentInstance.approved_config_id)
                      .where(AgentInstance.organization_id == org_id, AgentInstance.status == "active",
                             TaskDefinition.trigger_type == "event", TaskDefinition.event == event)).all()
    if not rows:
        return 0
    profile = company.get_profile(db, org_id)
    now = datetime.now(UTC)
    created = 0
    for task, inst, cfg in rows:
        not_before = None
        if cfg.config["operating"]["execution_window"] == "business_hours" and profile.timezone:
            at = schedule.defer_to_business_hours(now, profile.timezone, profile.operating_schedule,
                                                  schedule.holiday_dates(profile.holidays))
            not_before = at if at and at > now else None
        run = new_run(db, inst, task_key=task.key, task_title=task.title, trigger_type="event",
                      trigger={"event": event, "subject_type": subject_type, "subject_id": str(subject_id), **extra},
                      idempotency_key=f"event:{event}:{subject_id}:{inst.id}:{task.key}",
                      lock_key=f"{inst.id}:{task.key}:{subject_id}", not_before=not_before)
        created += run is not None
    return created
