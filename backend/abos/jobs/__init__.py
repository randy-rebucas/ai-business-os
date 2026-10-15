"""Background jobs (ADR-008): durable state in `job_runs` (Postgres), Celery + Redis only deliver the wake-up.

- `enqueue()` adds a JobRun to the caller's transaction; the Celery message is sent only after that commit, so a
  worker never sees a job whose row doesn't exist yet. With ABOS_JOBS_EAGER the job runs inline after commit.
- `run_job()` claims the row with SELECT … FOR UPDATE SKIP LOCKED, so duplicate deliveries can't run it twice.
- `sweep()` re-sends queued jobs whose message was lost and fails/retries running jobs whose heartbeat stopped.

Worker:  celery -A abos.jobs.worker worker --pool=solo --loglevel=info      (Windows needs --pool=solo)
Sweeper: celery -A abos.jobs.worker beat   (or `python -m abos.jobs sweep` from a scheduler)
"""
