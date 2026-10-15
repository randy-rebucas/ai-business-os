# Operations: observability, data controls, backup & recovery

Audience: whoever runs the platform. Deployment itself is in `DEPLOYMENT.md`; decisions in `DECISIONS.md`
(ADR-032 metrics, ADR-033 data controls, ADR-034 route checks).

## 1. Observability

### Logs
Every process logs one JSON object per line to stdout (`abos/core/logging.py`):
`ts, level, logger, msg, request_id` plus correlation fields.

| Where | Fields added |
|---|---|
| API request | `request_id` (from `X-Request-Id` or generated, echoed in the response), `method`, `path` (no query string), `route` (template), `status`, `ms` |
| Background job | `job_id`, `job_kind`, `org_id`, `target_id` (the document/run/delivery/export) |
| Agent run step | the above + `run_id` |

Users quote the `request_id` shown in error messages; search logs for it.

### Error reporting
All unhandled errors — API requests and background jobs (except `JobFailed`, which means bad input) — go through
`abos.core.errors.report_exception`: an `ERROR` log line with the stack and correlation fields, the
`abos_unhandled_errors_total{where=api|job|housekeeping}` counter, and any registered reporter. Clients get a generic
500 with the request id; no internals. Optional Sentry: `pip install ".[monitoring]"`, `ABOS_ERROR_REPORTER=sentry`,
`ABOS_SENTRY_DSN` (no PII, no bodies; **not verified against a live Sentry project**). `/api/health/ready` shows
which reporter is active.

### Metrics
`GET /api/metrics` with `Authorization: Bearer $ABOS_METRICS_TOKEN` (endpoint is 404 when no token is set).
Prometheus text format:

| Metric | Meaning |
|---|---|
| `abos_http_requests_total{method,route,status}` | API requests (this process) |
| `abos_http_request_duration_seconds` (histogram) | latency per route |
| `abos_unhandled_errors_total{where}` | reported errors (this process) |
| `abos_jobs{kind,status}` | queued/running now; succeeded/failed in the last 24 h (all processes, from the DB) |
| `abos_jobs_oldest_queued_seconds` | queue lag — alert if it grows (worker down / Redis lost) |
| `abos_workflow_runs_24h{status}`, `abos_tool_executions_24h{status}` | agent work |
| `abos_notification_deliveries_24h{channel,status}` | email/SMS outcomes (watch `failed`, `abandoned`) |
| `abos_documents{status}`, `abos_action_requests_pending` | ingestion state, human approvals waiting |
| `abos_database_up` | metrics queries reached the DB |

Suggested alerts: `abos_database_up == 0`; `abos_jobs_oldest_queued_seconds > 600`;
`increase(abos_unhandled_errors_total[15m]) > 0`; `abos_jobs{status="failed"}` rising;
`abos_notification_deliveries_24h{status="abandoned"} > 0`; p95 latency per route.
Health: `/api/health` (liveness), `/api/health/ready` (DB, RLS role, adapters — dev adapters are labelled).

## 2. Background schedules (Celery beat → worker)

| Task | Every | Does |
|---|---|---|
| `abos.sweep` | 2 min | re-dispatches lost jobs, fails timed-out ones |
| `abos.schedule_tick` | 1 min | scheduled agent tasks, overdue events, deferred runs, reconciliation, delivery retries, final reports, digests |
| `abos.housekeeping` | 1 h | due workspace deletions, expired exports, retention purges |

Each also runs once from the CLI: `python -m abos.jobs sweep|tick|housekeeping` (prints a JSON summary).

## 3. Data retention & deletion (SPEC §6)

### Retention (Settings → Data & privacy; `GET/PUT /api/v1/org/retention`)
| Data | Default | Configurable |
|---|---|---|
| Notifications (+ their deliveries) | 180 days | 30–3650 days, per workspace |
| Ask history (`knowledge_queries`) | 365 days | 30–3650 days |
| Daily reports (+ evidence index) | kept | 90–3650 days or keep |
| Finished background jobs | 90 days | `ABOS_JOB_RUNS_RETENTION_DAYS` |
| Expired/revoked sessions, used tokens | 30 days after expiry | `ABOS_SESSIONS_RETENTION_DAYS` |
| Authentication events | 365 days | `ABOS_AUTH_EVENTS_RETENTION_DAYS` |
| Email outbox rows (sent/failed/dev-stored) | 90 days | `ABOS_OUTBOX_RETENTION_DAYS` |
| Rate-limit windows | 1 day | — |
| Workspace exports | 72 h | `ABOS_EXPORT_TTL_HOURS` |

Kept while the workspace exists (no purge): audit log, agent run evidence (tool executions, reconciliations),
approvals, business records (invoices, payments, expenses, drafts), model usage (budgets), documents (until archived
or the workspace is deleted), configurations and their versions.

### Export (`POST /api/v1/org/exports`, owner only, 5 per day)
A job writes a zip to private storage: `manifest.json`, `workspace.json`, `members.json` (no credentials),
`tables/<table>.json` for every tenant table (read through the RLS-bound session and filtered by workspace), and the
original document files under `files/`. Search embeddings are omitted (re-indexing rebuilds them). Requests and
downloads are audited. The archive is built in memory — fine at MVP volumes; stream to storage before very large
tenants.

### Workspace deletion (`POST/DELETE /api/v1/org/deletion`, owner only)
1. An owner types the exact workspace name and their password → deletion is scheduled
   `ABOS_ORG_DELETION_GRACE_HOURS` (72) later; every owner is emailed; every member sees a banner.
2. Any owner can cancel until then.
3. Housekeeping deletes it on the owner path (`ABOS_MAINTENANCE_DATABASE_URL`): one transaction removes the
   `organizations` row and, by FK cascade, every tenant row — including write-once evidence and insert-only ledgers —
   then the document files and exports are deleted. An `organization_deletions` row records row counts and file
   counts (no tenant data). Audit events remain with the workspace link removed.
4. People keep their accounts and other workspaces.

A file that can't be deleted is counted in `files_failed` and reported; configure an S3 lifecycle rule on the bucket
prefix `<org_id>/` as a backstop.

## 4. Backup & recovery

### What to back up
| Component | How | Notes |
|---|---|---|
| Postgres (everything: data, RLS policies, triggers, grants, migration revision) | `infra/backup/backup.sh` (pg_dump custom format) nightly + managed point-in-time recovery if available | connect as the table owner — the app role would see nothing through RLS |
| Object storage | S3: bucket versioning + cross-region replication. Local: `STORAGE_DIR=... backup.sh` tars it | documents and exports |
| Redis | not needed | only wake-up messages; the sweeper re-sends queued jobs from Postgres |
| Secrets (env file) | your secret manager | never in backups next to data |

Targets (suggested): RPO ≤ 24 h with nightly dumps (≤ 5 min with managed PITR), RTO ≤ 2 h. Keep 7 daily, 4 weekly,
12 monthly copies, encrypted, in a different account/region. Deleted workspaces reappear if an older backup is
restored — after a restore, re-run housekeeping deletions from `organization_deletions` (delete those organization
ids again) before opening the restored system.

### Backup
```bash
# production (pg_dump on the path, owner login in PG* variables)
PGHOST=db PGUSER=abos_owner PGPASSWORD=... PGDATABASE=abos infra/backup/backup.sh /backups
# local dev (Docker)
PG_DUMP="docker compose exec -T postgres pg_dump -U abos" PSQL="docker compose exec -T postgres psql -U abos" \
  PGDATABASE=abos STORAGE_DIR=backend/storage infra/backup/backup.sh ./backups
```
Output: `abos-<UTC stamp>/` with `database.dump`, `storage.tar.gz` (local storage only), `alembic_revision`,
`row_counts.tsv`, `SHA256SUMS`.

### Restore (always into a new database, then switch)
```bash
PG_RESTORE="docker compose exec -T postgres pg_restore -U abos" PSQL="docker compose exec -T postgres psql -U abos" \
  PGDATABASE=postgres infra/backup/restore.sh ./backups/abos-<stamp> abos_restored
```
The script verifies checksums, refuses an existing database, restores in one transaction, then checks the migration
revision, the row count of every table against the backup, and reports the RLS policies and ledger triggers present.
Then: extract `storage.tar.gz` into `ABOS_STORAGE_DIR` (or restore the S3 bucket version), point
`ABOS_DATABASE_URL`/`ABOS_MAINTENANCE_DATABASE_URL` at the new database, start API/worker/beat, check
`/api/health/ready` (`db_role.rls_enforced: true`), and replay deletions (above).

**Drill record:** 2026-10-15 — dev database backed up and restored into `abos_restore_check`: revision 0007, all 55
tables with identical row counts, 44 RLS policies and both ledger triggers present; `abos_app` saw 0 documents without
a tenant while the owner saw 34; the storage archive extracted identical (36/36 files). Repeat the drill quarterly and
after every migration that adds a table.
