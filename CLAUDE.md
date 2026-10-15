# AI Business OS — project memory

READ FIRST every session: `docs/STATUS.md` (current phase, next steps, session log), then `docs/PHASES.md`
(checklist), `docs/DECISIONS.md` (don't re-litigate settled ADRs), `docs/ARCHITECTURE.md`.
Full requirements: `docs/SPEC.md` (the original master prompt — authoritative).

## Rules
- Work one phase at a time (SPEC §10). At the end of every session: tick verified items in `docs/PHASES.md`,
  append to the `docs/STATUS.md` session log, add an ADR for any non-obvious choice.
- Never tick a box or claim an integration works without a passing test or recorded live verification.
  Dev adapters (mail outbox, later LLM/embeddings) must stay labelled as such.
- Business logic lives in `service.py`, never in routers or React components.
- Tenant data: authorize with `require_org_member` / `require_org_permission` — never trust org ids from bodies.
  New tenant tables use `TenantMixin` and call `migration_sql.enable_tenant_rls(op, table)` in their migration
  (`tests/test_rls.py` enforces it). Cross-tenant jobs use `abos.core.tenancy.system_scope()`.
- Permissions are checked by name (`identity/permissions.py`), never by role. Job title grants nothing.
- AI is never the source of truth for money, permissions, statuses or quantities (SPEC §2).
- UI shows only real backend data; no fake stats, no controls without a working endpoint.

## Commands (Windows / PowerShell 5.1)
- Infra: `docker compose up -d postgres redis` (Postgres 127.0.0.1:55470 dbs `abos` + `abos_test`; Redis 56470)
- Backend venv: `backend\.venv\Scripts\python.exe` (Python 3.12)
- Migrate: `cd backend; .venv\Scripts\alembic upgrade head` · new migration:
  `.venv\Scripts\alembic revision --autogenerate -m "..." --rev-id 000N` then add RLS calls by hand
- Seed: `cd backend; .venv\Scripts\python -m abos.seed` → `ceo@abos-dev.example.com` / `dev-password-change-me`
- API: `cd backend; .venv\Scripts\uvicorn abos.main:app --port 8470 --timeout-keep-alive 75` (docs at
  http://127.0.0.1:8470/api/docs; the keep-alive avoids ECONNRESET 500s through Next's proxy). For a full Playwright run
  set `$env:ABOS_RL_REGISTER_IP='500/3600'` first — every spec registers from 127.0.0.1
- Worker (needed unless ABOS_JOBS_EAGER=true): `cd backend; .venv\Scripts\celery -A abos.jobs.worker worker --pool=solo -Q abos --loglevel=info`
  · sweeper: `.venv\Scripts\python -m abos.jobs sweep` · scheduler tick (due schedules, overdue events, deferred
  runs): `.venv\Scripts\python -m abos.jobs tick` (both run under `celery -A abos.jobs.worker beat`)
  · housekeeping (deletions, retention purges, expired exports): `.venv\Scripts\python -m abos.jobs housekeeping`
- `/api/health/ready` shows db role/RLS, jobs mode, storage, error reporter, and which AI adapters are active (dev = labelled)
- Metrics: set `ABOS_METRICS_TOKEN`, then `GET /api/metrics` with `Authorization: Bearer <token>`
- Backup/restore (Git Bash): `infra/backup/backup.sh <dir>` / `restore.sh <dir> <new-db>` — see docs/OPERATIONS.md §4
- Images: `docker build -t abos-backend backend` · `docker build -t abos-web frontend`; prod topology
  `infra/deploy/compose.prod.yml`, docs/DEPLOYMENT.md; CI `.github/workflows/ci.yml`
- Tests: `cd backend; .venv\Scripts\pytest -q` (uses `abos_test`, migrates down/up each run) · lint: `.venv\Scripts\ruff check .`
- Frontend: `cd frontend; npm run dev` (:3470) · `npm run build` · `npm run start` · `npm run lint` · `npm run typecheck`
- Browser E2E (API + `next start` running): `cd frontend; npx playwright test` (installed Chrome, axe gate,
  screenshots → `frontend/test-results/shots/`; creates a fresh workspace per run in the dev DB)

## Knowledge / AI rules that tests enforce (don't weaken)
- Only `status='indexed'` documents are retrievable; filters (org, status, current version, access level) live in
  the retrieval SQL (ADR-013). Access levels: `documents.allowed_levels`.
- Answers are verified deterministically (`knowledge/answer._verify`): fabricated citations dropped, unsupported
  figures → `unsupported`. Instruction-like document text is redacted before any model sees it (`safety.redact`).
- Dev adapters (`llm_provider=dev`, `embedding_provider=hash`) must stay labelled; production refuses them.
  Real Claude calls are billed — ask the user before running anything with ABOS_LLM_PROVIDER=anthropic.
- Never `GRANT ... ON ALL TABLES` in a migration: it re-grants UPDATE/DELETE on append-only tables
  (test_audit catches it). New tables get privileges from default privileges.
- Use `migration_sql.revoke_rewrite` (not the trigger) for ledgers that must cascade-delete with their org.

## Agents / governance rules that tests enforce (don't weaken)
- `agents/catalog_v1.py` is frozen (migration 0003 imports it): new catalog content = `catalog_vN.py` + a migration.
- Permission scopes/ceilings live only in `agents/policy.py`; a mode above the platform or definition ceiling is an
  error on submit and on approval. Permissions, triggers, schedules, budgets never come from model output.
- Submitted/approved/rejected configurations are frozen; decisions must carry the reviewed `config_hash`.
  Real tool calls go through `orchestration.service._call`, which calls `agents.service.execution_allowed()` before
  the dispatcher and again right before the tool runs.
- Only `confirmed`, non-stale business rules feed configurations; rule figures must appear in the quoted source.
- Simulation (`abos/simulation`): every tool call goes through `Sandbox.call` (the governance dispatcher Phase 5
  reuses); grading is deterministic; mandatory checks override scores. Bump `library.LIBRARY_VERSION` when a library
  scenario changes. Test suggestions may only narrow access (ADR-024). Activation starts in observation.

## Execution rules that tests enforce (don't weaken) — see `docs/EXECUTION.md`
- One decision path: `governance/dispatch.decide` serves both the sandbox and real execution — never fork it.
- Tools exist only in `tools/registry.py` (bump `REGISTRY_VERSION` when a tool's contract changes). No SQL/shell/HTTP
  tool. A tool without a real integration is registered as not connected, never faked.
- Held actions are approved by `params_hash` over the *resolved* parameters + config hash + policy version; any change
  supersedes the approval. External sends are approval "always".
- `tool_executions` is write-once (only a `started` row may be completed, once); runs can't be deleted; payments and
  invoice lines are insert-only. Side effects carry an idempotency key; an unknown outcome is `unverified`, never
  success and never retried. Run summaries are figure-checked against tool results.
- Money comes from `business/calculations.py` (Decimal); never add amounts across currencies.

## Reporting / notification rules that tests enforce (don't weaken) — see `docs/REPORTING.md`
- Daily reports are deterministic projections of runs / ledger / requests / reconciliations / usage — never model text.
  Attempted ≠ completed: only `succeeded`, or `unverified` confirmed by an `execution_reconciliations` row, counts.
  Never rewrite a ledger row to settle an outcome; insert a reconciliation.
- Notification recipients are chosen by permission (`notifications.service.RECIPIENT_PERMISSION`), never by role.
  Emails/SMS are `notification_deliveries` rows sent by jobs after commit; dev providers store and are labelled; no
  messaging provider is hard-coded (SMS = `SmsProvider` adapter).
- Agent `monthly_budget_usd` is enforced at run claim from `model_usage`; the company budget is compared only in USD.

## Hardening rules that tests enforce (don't weaken) — see `docs/SECURITY.md`, `docs/OPERATIONS.md`
- `tests/test_security_surface.py` walks every route: new routes need `current_auth` (or a deliberate PUBLIC entry),
  a named permission (`require_org_permission`), no data change behind `*.read`, and `ai_work()` if they start model
  calls or worker jobs. Keep its allow-lists honest.
- Workspace deletion / purges run only in housekeeping on the owner path (`privacy/maintenance.py`); never give the API
  `ABOS_MAINTENANCE_DATABASE_URL`. Tables named with `organization_id` are tenant tables (export, deletion counts,
  RLS test) — a platform table that references a deleted org uses another column name.
- List/dashboard/report endpoints must keep constant query counts (`tests/test_performance.py`) — batch, don't loop.
- Log context: jobs carry `job_id/job_kind/org_id/target_id` (+ `run_id`); errors go through `report_exception`.

## Design rules (Phase 8 — PRODUCT.md, DESIGN.md, ADR-035; tests enforce the contrast parts)
- Colours come from tokens in `frontend/src/app/globals.css`; tenants may only change `--brand-*` (accent, fill, note,
  marker) and `--mood-*` (fonts) via `lib/branding.tsx`. Never let tenant colour reach status colours or the rail.
- Filled controls use `bg-accent-fill text-on-accent-fill`; text links/focus use `text-accent`. Text on a tenant
  marker colour is forbidden (only 3:1 guaranteed).
- Accent derivation lives in `abos/branding/colors.py`; a new surface colour must be added to its fit targets and to
  `tests/test_branding.py`'s surface lists.
- Report figures use `components/ui/report.tsx` (Figures/Figure/Notes/ReportSection); every note must describe real
  data and link to real records. No eyebrow labels above headings; context lines go under the title.

## Gotchas
- SQLAlchemy fires `after_commit`/`after_rollback` on SAVEPOINT release/rollback too — after-commit hooks must skip
  `session.in_nested_transaction()` (jobs and mailer do).
- Compare timestamps from the same clock: the Docker DB clock can differ from the host (use `func.now()` when a value
  is compared with server-default timestamps).
- Test cleanup skips migration-seeded tables (`tests/conftest.SEEDED_BY_MIGRATIONS`) — add new seeded tables there.
- The API runs as DB role `abos_app` (RLS). Tests inspect data via the `db` fixture (owner, no RLS); `app_db` is
  RLS-bound. `/api/health/ready` shows `db_role.rls_enforced`.
- `audit_events` is append-only (trigger + no UPDATE/DELETE grant). Test cleanup truncates with
  `session_replication_role=replica`.
- IntegrityError can fire at `flush()`, not just `commit()` — wrap both (see `company.service._unique_guard`).
- PATCH schemas from `_partial()` lose validators: services merge the patch into the row and re-validate with the
  full create schema.
- Next.js 16: read `frontend/node_modules/next/dist/docs/` before unfamiliar APIs; `error.tsx` gets `retry`;
  `useSearchParams` pages need `<Suspense>`; middleware is `src/proxy.ts` (nonce CSP); zod must stay `jitless`.
- React-compiler lint forbids setState in effects — key components by data version instead.
- `next start` must be restarted after `npm run build` (kill the PID listening on 3470 first).
- npm is very slow on this machine; node_modules was seeded by copying from ~/projects/gsm-ai-technician/frontend.
- PS 5.1: no `&&`; `Set-Content`/`Get-Content` mangle UTF-8 → edit files with Edit/Write tools only;
  git commit messages → `git commit -F <file>`.
- FastAPI 0.143 nests included routers (`_IncludedRouter`); enumerate routes via `original_router.routes`
  (see `test_security_surface._routes`), not `app.routes`.
- Killing uvicorn/celery on Windows: match `ai-business-os\backend\.venv\Scripts\(uvicorn|celery)` in the command line —
  the launcher shim leaves a child python that keeps the port.
- GNU tar (Git Bash) reads `C:/...` as host:path — write archives via stdout (`-f -`).
- Ports in use by other local projects: 5432, 6379, 8000, 15433, 55450, 55460, 56390, 8460, 3460.
