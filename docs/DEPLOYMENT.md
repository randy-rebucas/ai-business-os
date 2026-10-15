# Deployment

Audience: whoever deploys and operates the platform. Day-2 operations (metrics, retention, backups) are in
`OPERATIONS.md`; local development in the README / `CLAUDE.md`.

## 1. Components

| Process | Image / command | Scale | Needs |
|---|---|---|---|
| `api` | `backend/Dockerfile` (default CMD: uvicorn :8470) | horizontally | Postgres (app login), Redis, storage |
| `worker` | same image: `celery -A abos.jobs.worker worker -Q abos` | horizontally | + `ABOS_MAINTENANCE_DATABASE_URL` (housekeeping) |
| `beat` | same image: `celery -A abos.jobs.worker beat` | **exactly one** | Redis |
| `migrate` | same image: `alembic upgrade head` (one-shot, every deploy, before the rest) | — | owner login |
| `web` | `frontend/Dockerfile` (Next standalone :3470); `/api/*` is proxied to `ABOS_API_ORIGIN` (build arg) | horizontally | api |
| Postgres 16 + pgvector | managed or `pgvector/pgvector:pg16` | — | extension `vector` |
| Redis 7 | managed or `redis:7.4-alpine` | — | AOF optional (state lives in Postgres) |
| S3-compatible bucket | private, SSE, versioning on | — | `ABOS_STORAGE_BACKEND=s3`, image built with `EXTRAS=s3` |

Example single-host topology: `infra/deploy/compose.prod.yml`. Put a TLS-terminating proxy in front of `web` only;
never expose `api` (it trusts `X-Forwarded-For` from `FORWARDED_ALLOW_IPS`).

## 2. Database roles (ADR-003, ADR-033)

| Login | Used by | Rights |
|---|---|---|
| owner (e.g. `abos_owner`) | `migrate`, `worker` housekeeping (`ABOS_MAINTENANCE_DATABASE_URL`), backups | owns the tables |
| app (e.g. `abos_api`) | `api`, `worker` jobs (`ABOS_DATABASE_URL`) | member of `abos_app` only (NOINHERIT); the app does `SET ROLE abos_app`, so RLS applies |

```sql
-- once, as an admin, before the first migration (managed Postgres without CREATEROLE for the owner):
CREATE ROLE abos_app NOLOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT;
CREATE ROLE abos_owner LOGIN PASSWORD '...';
CREATE ROLE abos_api LOGIN PASSWORD '...' NOINHERIT IN ROLE abos_app;
GRANT abos_app TO abos_owner;
CREATE DATABASE abos OWNER abos_owner;
\c abos
CREATE EXTENSION vector;
```
The API refuses to start in production if its effective role can bypass RLS.

## 3. Configuration

All settings are `ABOS_*` environment variables (`backend/.env.example`, `abos/core/config.py`). With
`ABOS_ENV=production` the API/worker **refuse to start** unless: `ABOS_COOKIE_SECURE=true`,
`ABOS_SESSION_COOKIE_NAME=__Host-…`, https `ABOS_APP_BASE_URL`, a non-dev DB password, `ABOS_MAILER=smtp` with
`ABOS_SMTP_HOST`, real AI providers (`ABOS_LLM_PROVIDER=anthropic` + key, `ABOS_EMBEDDING_PROVIDER=voyage|openai` +
key), `ABOS_SMS_PROVIDER=none` (no real SMS provider exists yet), `ABOS_STORAGE_BACKEND=s3`, `ABOS_JOBS_EAGER=false`,
rate limits on, and a DSN if Sentry is selected. Housekeeping refuses to run in production without
`ABOS_MAINTENANCE_DATABASE_URL`. Keep secrets in a secret manager / env file outside the repo; settings never print
secrets (DB URL and keys are excluded from `repr`).

Also set: `ABOS_METRICS_TOKEN` (scraping), `FORWARDED_ALLOW_IPS` on `api` (your proxy / web addresses), and
`ABOS_API_ORIGIN` as a build arg of the web image.

**Before the first production start** (see STATUS.md "Known limitations"): the real Claude and embedding adapters,
SMTP, S3 and Sentry have **not** been verified live; run the knowledge eval suite after switching embeddings
(ADR-016) and reprocess documents.

## 4. Release procedure
1. CI green (`.github/workflows/ci.yml`: ruff, migration drift check, pytest against Postgres+Redis, frontend
   lint/typecheck/build, Playwright journeys against the full stack with the axe gate, both images build).
2. Back up (`OPERATIONS.md` §4).
3. `docker compose run --rm migrate` (migrations are transactional; each has a tested downgrade).
4. Roll `api`, `worker`, `web`; restart `beat` last (one instance). Running jobs survive: claims are row-locked and the
   sweeper requeues work from a worker that disappeared.
5. Check `/api/health/ready` and the metrics (`abos_jobs_oldest_queued_seconds`, error counter).
Rollback: redeploy the previous images; `alembic downgrade <rev>` only if the new revision must go (restore from the
backup if data was written in a shape the old code can't read).

## 5. Capacity & cost notes
- Every list/dashboard/report endpoint runs a bounded number of queries regardless of data size
  (`tests/test_performance.py`); period queries use `(organization_id, created_at)` indexes.
- Model spend is capped per agent by `limits.monthly_budget_usd` (enforced at run claim) and per user/workspace by the
  `ai_work` rate limits; usage & costs page shows estimates from the gateway's price table.
- Workers: `--concurrency` per CPU; runs are step-wise and I/O-bound on model calls. Exports are built in memory.
