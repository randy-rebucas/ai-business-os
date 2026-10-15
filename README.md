# AI Business OS

A SaaS platform where a CEO onboards their company, hires specialised AI employees, grounds them in company
knowledge (RAG), tests them in simulations, approves their permissions and supervises their work through
evidence-backed reports. Requirements: [docs/SPEC.md](docs/SPEC.md). Progress: [docs/STATUS.md](docs/STATUS.md).

## Stack
FastAPI · SQLAlchemy 2 · Alembic · Celery · PostgreSQL 16 + pgvector · Redis · Next.js 16 · React 19 · Tailwind v4.

| Process | Address | Started by |
|---|---|---|
| Postgres (dbs `abos`, `abos_test`) | 127.0.0.1:55470 | `docker compose` |
| Redis | 127.0.0.1:56470 | `docker compose` |
| API (FastAPI) | http://127.0.0.1:8470 — docs at `/api/docs` | `uvicorn` |
| Worker (Celery) | — | `celery` |
| Web (Next.js) | http://localhost:3470 | `npm run dev` |

The web app proxies `/api/*` to the API (`ABOS_API_ORIGIN`, default `http://127.0.0.1:8470`), so the session cookie
stays first-party. Open the app on :3470, not the API directly.

## Prerequisites
- Docker Desktop (for Postgres + Redis)
- Python 3.12 (`py -3.12 --version` on Windows)
- Node.js 20+ and npm

## Local setup

### Shell note
Commands below are for **PowerShell**. In **Git Bash**, `\` is an escape character, so `.venv\Scripts\uvicorn`
turns into `.venvScriptsuvicorn: command not found` — use forward slashes instead (`.venv/Scripts/uvicorn`) and
`cp` instead of `copy`. PowerShell 5.1 also has no `&&`; run commands one per line or separate them with `;`.

### 1. Database and Redis
```powershell
docker compose up -d postgres redis
```
Both ports bind to 127.0.0.1 only. Override them with `ABOS_DB_PORT` / `ABOS_REDIS_PORT` if they clash.

### 2. Backend
```powershell
cd backend
py -3.12 -m venv .venv
.venv/Scripts/pip install -e ".[dev]"
copy .env.example .env               # every setting is documented in .env.example and abos/core/config.py
.venv/Scripts/alembic upgrade head   # creates the schema and row-level security policies
.venv/Scripts/python -m abos.seed    # dev workspace + CEO login; safe to re-run ("already seeded")
```
`.env` is optional — the defaults already match the Docker setup. Restart the API and worker after editing it.

If `py -m venv` fails with `Permission denied ... python.exe`, the API or worker is still running from that venv.
Stop them first (the venv already exists if it got that far, so you can usually skip this step).

### 3. Run the API and the worker (two terminals, both in `backend`)
```powershell
.venv/Scripts/uvicorn abos.main:app --port 8470 --timeout-keep-alive 75
```
```powershell
.venv/Scripts/celery -A abos.jobs.worker worker --pool=solo -Q abos --loglevel=info
```
- `--timeout-keep-alive 75` avoids intermittent 500s (ECONNRESET) through the Next.js proxy.
- The worker runs document ingestion, simulations, agent runs, reports and notifications. To skip it during quick
  local work, set `ABOS_JOBS_EAGER=true` in `.env` (jobs then run inside the API request).
- Scheduled work (due schedules, overdue events, deferred runs, sweeps, housekeeping) runs under
  `.venv\Scripts\celery -A abos.jobs.worker beat`, or one-off with `.venv\Scripts\python -m abos.jobs tick`,
  `... sweep` or `... housekeeping`.
- Check everything is wired up: http://127.0.0.1:8470/api/health/ready (database role and RLS, job mode, storage,
  error reporter, active AI adapters).

### 4. Frontend
```powershell
cd frontend
npm install
npm run dev                          # http://localhost:3470
```
For a production-like run: `npm run build` then `npm run start` (restart `start` after every build).

### 5. Log in
Dev login: `ceo@abos-dev.example.com` / `dev-password-change-me` (change with `ABOS_SEED_PASSWORD`).

## Development adapters
Out of the box nothing leaves your machine. Each dev adapter is labelled in `/api/health/ready`, and production
refuses to start with them:

| Area | Dev default | Real option |
|---|---|---|
| Email | `ABOS_MAILER=dev_outbox` — stored in the `email_outbox` table (verification and reset links are there) | `smtp` |
| LLM | `ABOS_LLM_PROVIDER=dev` — no model calls | `anthropic` + `ABOS_ANTHROPIC_API_KEY` (billed) |
| Embeddings | `ABOS_EMBEDDING_PROVIDER=hash` | a real provider + `ABOS_EMBEDDING_MODEL` / key |
| SMS | `ABOS_SMS_PROVIDER=dev` — stored, not sent | provider adapter, or `none` |
| File storage | `ABOS_STORAGE_BACKEND=local` — files under `backend/storage` | `s3` (`pip install boto3`) |

## Database migrations
```powershell
cd backend
.venv\Scripts\alembic upgrade head
.venv\Scripts\alembic revision --autogenerate -m "describe change" --rev-id 000N
```
New tenant tables must use `TenantMixin` and call `migration_sql.enable_tenant_rls(op, table)` in their migration —
add that by hand after autogenerate. `tests/test_rls.py` fails otherwise.

## Tests
- Backend (uses the `abos_test` database; migrates down/up each run):
  `cd backend; .venv\Scripts\pytest -q` and `.venv\Scripts\ruff check .`
- Frontend: `npm run lint`, `npm run typecheck`, `npm run build`
- Browser E2E (API and `next start` running): `cd frontend; npx playwright test`. Every spec registers a user from
  127.0.0.1, so start the API with `$env:ABOS_RL_REGISTER_IP='500/3600'` for a full run. Each run creates a fresh
  workspace in the dev database; screenshots land in `frontend/test-results/shots/`.

## Operations
- Metrics: set `ABOS_METRICS_TOKEN`, then `GET /api/metrics` with `Authorization: Bearer <token>`.
- Backup / restore (Git Bash): `infra/backup/backup.sh <dir>` / `infra/backup/restore.sh <dir> <new-db>` —
  see [Operations](docs/OPERATIONS.md).
- Images: `docker build -t abos-backend backend` · `docker build -t abos-web frontend`. Production topology:
  `infra/deploy/compose.prod.yml` — see [Deployment](docs/DEPLOYMENT.md). CI: `.github/workflows/ci.yml`.

## Troubleshooting
| Symptom | Fix |
|---|---|
| `bash: .venvScriptsuvicorn: command not found` | You're in Git Bash — use `.venv/Scripts/uvicorn`. |
| `address already in use` on 8470 / 3470 | Another API or web server is running. Stop it, or check `Get-NetTCPConnection -LocalPort 8470`. |
| `Permission denied` on `.venv\Scripts\python.exe` | The API/worker is running from the venv — stop it first. On Windows, kill the child `python.exe` too; the launcher leaves one holding the port. |
| Uploads/simulations/runs stay queued | The worker isn't running (or set `ABOS_JOBS_EAGER=true`). |
| Can't connect to Postgres | `docker compose ps` — the containers must be healthy, and port 55470 free. |
| Red `NativeCommandError` around Alembic output in PowerShell | Harmless: PowerShell 5.1 wraps Alembic's stderr logging. Check the exit code instead. |

## Docs
[Architecture](docs/ARCHITECTURE.md) · [Phases](docs/PHASES.md) · [Decisions](docs/DECISIONS.md) ·
[Status & session log](docs/STATUS.md) · [Security](docs/SECURITY.md) · [Operations & backups](docs/OPERATIONS.md) ·
[Deployment](docs/DEPLOYMENT.md) · RAG / agents / simulation / execution / reporting:
[RAG](docs/RAG.md), [AGENTS](docs/AGENTS.md), [SIMULATION](docs/SIMULATION.md), [EXECUTION](docs/EXECUTION.md),
[REPORTING](docs/REPORTING.md)
