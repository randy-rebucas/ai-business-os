"""Celery application. Start with: celery -A abos.jobs.worker worker --pool=solo --loglevel=info"""

import uuid

from celery import Celery

from abos import models  # noqa: F401  (registers all ORM models)
from abos.core.config import get_settings
from abos.core.errors import install_error_reporter
from abos.core.logging import configure_logging
from abos.jobs import service
from abos.knowledge import ingest  # noqa: F401  (registers job handlers)
from abos.notifications import service as notifications  # noqa: F401  (registers job handlers)
from abos.orchestration import scheduler
from abos.orchestration import service as orchestration  # noqa: F401  (registers job handlers)
from abos.privacy import housekeeping  # (also registers the export job handler)
from abos.simulation import service as simulation  # noqa: F401  (registers job handlers)

configure_logging(get_settings().log_level)
install_error_reporter(get_settings())

app = Celery("abos", broker=get_settings().redis_url)
app.conf.update(
    task_acks_late=True,              # a crashed worker's message is redelivered; the row lock prevents double runs
    worker_prefetch_multiplier=1,
    task_default_queue="abos",
    broker_connection_retry_on_startup=True,
    worker_hijack_root_logger=False,  # keep the JSON log format
    beat_schedule={"sweep-jobs": {"task": "abos.sweep", "schedule": 120.0},
                   "schedule-tick": {"task": "abos.schedule_tick", "schedule": 60.0},
                   "housekeeping": {"task": "abos.housekeeping", "schedule": 3600.0}},
)


@app.task(name="abos.run_job")
def run_job_task(job_id: str) -> str:
    return service.run_job(uuid.UUID(job_id))


@app.task(name="abos.sweep")
def sweep_task() -> dict:
    return service.sweep()


@app.task(name="abos.schedule_tick")
def schedule_tick_task() -> dict:
    return scheduler.tick()


@app.task(name="abos.housekeeping")
def housekeeping_task() -> dict:
    return housekeeping.run()
