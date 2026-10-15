# Status

**Current phase:** Phase 8 (Design: platform identity + tenant branding) built and verified locally, on top of SPEC
§10's seven phases (live-integration caveats below). Finish review ended at disposition **fix** with three small
layout items open (see the Phase 8 session log). **Next:** decide on those three items, then push to a GitHub remote and
get CI green, then the production blockers in "Next session".

## Where things stand
- Phase 0 — architecture, plan, ADRs, schema/API contracts.
- Phase 1 — SaaS foundation: auth, workspaces (Owner + separate job title), org-scoped authorization + Postgres RLS,
  members, company profile + 8 collections + completeness, append-only audit, onboarding wizard, dashboard, settings.
- Phase 2 — business knowledge & RAG: document upload/URL import → background ingestion (Celery/Redis, durable job
  state) → review gate → hybrid retrieval → verified, cited answers; RAG eval suite; business interview. See
  `docs/RAG.md`.
- Phase 3 — AI workforce: catalog A–H (DB, versioned), recommended/custom team, hiring, lifecycle state machine,
  business-rule extraction & review, job description + task generation, editable versioned configurations with
  context validation and schedule preview, CEO approval bound to config hash + policy version, execution guard.
  See `docs/AGENTS.md`.
- Phase 4 — simulation & readiness: per-agent scenario library (14 SPEC categories), sandboxed tools behind the
  governance dispatcher, background runs with traces, deterministic grading per dimension with per-agent thresholds and
  mandatory security checks, failure analysis with narrowing fixes, readiness gate, staged activation (observation →
  full), pause/resume with regression check, rollback. See `docs/SIMULATION.md`.
- Phase 5 — controlled execution: shared governance dispatcher (sandbox + real), code-defined tool registry, business
  records (invoices, payments, expenses, drafts), real finance/executive tools, step-wise orchestrator with labelled
  dev playbooks, approvals bound to exact parameters, events + scheduler, idempotency, write-once evidence ledger,
  unverified outcomes, one-level delegation. See `docs/EXECUTION.md`.
- Phase 6 — reporting & notifications: daily reports projected from execution records (15 sections, evidence index,
  attempted vs completed vs unverified, reconciliation), notifications by permission with preferences, limits,
  digests, delivery records and retries (email via the mailer, SMS adapter interface), Control Center with filters,
  usage & costs with enforced agent budgets. See `docs/REPORTING.md`.

- Phase 7 — hardening: route-walking security test (authn, named permission, rate limit on costly work, live
  anonymous/non-member/viewer denials for every route), `ai_work` rate limits, data controls (retention windows,
  owner-only export, scheduled workspace deletion on an owner DB path), observability (JSON logs with request/job/run
  ids, error sink, Prometheus metrics), constant query counts + indexes, backup/restore scripts with a restore drill,
  Dockerfiles, prod compose example, CI workflow, "Needs re-testing" for material changes, the SPEC §9 journey as one
  browser test. See `docs/SECURITY.md`, `docs/OPERATIONS.md`, `docs/DEPLOYMENT.md`.

## Next session
1. **Create the GitHub remote and run CI** (`.github/workflows/ci.yml` is written but has never run; nothing is
   committed yet — the repo has no commits). Fix whatever the clean Ubuntu runner surfaces.
2. Production blockers (each needs credentials / the user's go-ahead): real Claude + embeddings (**billed — ask
   first**; then reprocess documents and re-tune `ABOS_RETRIEVAL_MIN_VECTOR_SCORE` with the eval suite), SMTP, S3,
   Sentry; an SMS provider adapter; OCR (Tesseract); MFA/SSO; malware scanning of uploads.
3. Breadth after the MVP: integrations for the "not connected" catalog tools (CRM, tickets, inventory, HR …),
   playbooks/model planning for the other agents, KPI measurement sources.

## Verification record
| Date | Phase | Evidence |
|---|---|---|
| 2026-10-14 | 1 | pytest 42 passed; ruff clean; migrations up/down/up; lint/typecheck/build clean; Playwright 2 passed (+ axe on 6 pages); `/api/health/ready` → role `abos_app`, `rls_enforced: true` |
| 2026-10-14 | 2 | pytest **102 passed** (ingest, RAG, security, evals, AI layer, plus all Phase 1); ruff clean; migration 0002 up/down/up; lint/typecheck/build clean; Playwright **3 passed** — Phase 2 journey ran against the real stack with `ABOS_JOBS_EAGER=false`: Celery worker log shows `abos.run_job … succeeded` for each upload; axe clean on review, ask, evals, interview, documents pages |
| 2026-10-14 | 3 | pytest **175 passed** in 66 s (73 new: 41 unit — lifecycle, schedules/DST/holidays, validation, ceilings, hashing, templates; 20 agent API — catalog, recommendation, hiring, versioning, hash-bound approval, tamper detection, execution guard, roles, tenancy/RLS; 12 rules — verification, conflicts, staleness, injection, access levels); ruff clean; migration 0003 up/down/up; lint/typecheck/build clean; Playwright **4 passed** against the real stack (`ABOS_JOBS_EAGER=false`, worker log `abos.run_job … succeeded`): Phase 3 journey rules → team → hire → generate → edit → submit → approve, axe clean on rules, team, directory, agent profile (schedule + permissions tabs), configure, approval summary, approvals, catalog |
| 2026-10-14 | 4 | pytest **198 passed** (23 new: library coverage, dispatcher decisions, retries/tenancy/search filters, Decimal invoice checks, approved Finance suite → ready, unsafe Sales config fails mandatory checks → narrowing fix applied → re-approve → passes, suggestions never widen, retry-policy failure, activation/observation/widen/pause/resume/regression after rule change, rollback, custom scenarios, model-planner path via fake client, tenancy/roles, every one of the 8 agent templates passes its suite); ruff clean; migration 0004 up/down/up; lint/typecheck/build clean; Playwright **5 passed** against the real stack (`ABOS_JOBS_EAGER=false`, simulation runs executed by the Celery worker, no API/worker errors): readiness → run → passed → activate (observation) → pause/resume; failing Sales run → apply suggestion; axe clean on readiness, run (passed + failed), simulation center |
| 2026-10-15 | 5 | pytest **209 passed** (11 new: registry completeness/no escape hatch; records calculations, overpayment, duplicate references, insert-only payments/lines, roles, tenancy; invoice review end to end with evidence, drafts, escalation, draft reuse, write-once ledger, undeletable runs; idempotent requests, guard on pause and on a config changed behind the API; held send → policy change supersedes → re-approval → sent once → rejection recorded; events + overdue events + scheduler occurrences each once; transient retry, unknown outcome never success, crash-left `started` row → unverified, not repeated; model planner: unknown tool, invalid input, unsupported figure → unverified; Executive delegation one level; daily limit + business-hours release; tenant isolation incl. RLS); ruff clean; migration 0005 up/down/up; lint/typecheck/build clean; Playwright **6 passed** (all phases) against the real stack with `ABOS_JOBS_EAGER=false` — runs executed by the Celery worker (6 jobs `succeeded`, no API/worker errors): records form → invoice review → held send with exact text in the approval inbox → approve → run completed with every check passed → draft sent (dev outbox) → ad-hoc request → activity history; axe clean on records, run (awaiting + completed), approval inbox, drafts, agent activity; `python -m abos.jobs tick` ran live |
| 2026-10-15 | 6 | pytest **213 passed** (4 new, broad: daily report from records — all 15 sections, awaiting approval incl. the pending action, attempted = ran = completed, held attempt counted "not run", escalation, dev cost labelled, unmeasured KPIs said so, upcoming from the schedule, evidence index, rebuild → version 2, scheduler finalises the day once + report-ready notification, viewer can list but not read content; unverified SMTP send stays unverified until the outbox says sent → one insert-only reconciliation → completed, ledger row unchanged; notifications: recipients by permission (owner gets approvals, manager escalations only, viewer nothing, rival nothing), immediate email per preference (dev outbox, labelled), dedupe, critical → SMS through the dev adapter, hourly email limit → suppressed, failing provider → backoff retry → abandoned at max attempts, digest at the user's time in the company time zone once a day, read/unread, tenancy; Control Center counts, SLA overdue, escalations, performance, filters (priority, status, department, date), usage by agent with dev label, agent budget reached → run skipped + one budget notification, company budget in USD, usage needs `usage.read`); ruff clean; migration 0006 up/down/up; lint/typecheck/build clean; Playwright **7 passed** (all phases) against the real stack with `ABOS_JOBS_EAGER=false` (no API/worker errors): notifications inbox + unread badge, preferences (SMS dev-adapter label), escalation notification, today's report built from records, reports list, Control Center + status/priority filters, usage & budgets, agent Performance + Reports tabs; axe clean on each; `python -m abos.jobs tick` ran live (built 2 final reports, sent 8 digests to the dev outbox) |
| 2026-10-15 | 7 | pytest **552 passed** (339 new incl. parametrised: security surface — 330 cases walking every route statically + live anonymous/non-member/viewer denials, `ai_work` limits per user and per workspace, headers on every response kind, production settings guards, no secret in `repr`; privacy — retention bounds/audit/purge only past each workspace's window, export complete and isolated (no rival data, no credentials, no embeddings, files included, audited, expires and is removed), deletion confirmed by name+password, owners emailed, cancel, grace period, then every tenant row incl. write-once evidence and insert-only ledgers removed, audit detached, record + files deleted, rival untouched, accounts kept, app role can't read deletion records; observability — metrics token, route-template labels, no tenant data in labels, DB-derived job gauges, API and job errors reported once with correlation ids; performance — 24 endpoints + report build keep constant query counts as agents/runs/invoices/documents grow; continuous eval — rule change flags the active agent, resume blocked until regression run); ruff clean; migration 0007 up/down/up + `alembic check` no drift; lint/typecheck/build clean; Playwright **8 passed** against the real stack with `ABOS_JOBS_EAGER=false` (no API/worker errors, 22 worker jobs succeeded) — new `journey.spec.ts`: SPEC §9 steps 1–14 through the UI + rule confirmation + escalation notification + pause → edit → re-approve → re-test → resume + Needs re-testing + export download + schedule/cancel deletion, axe clean; backup → restore drill into a new DB (55 tables identical counts, RLS + triggers present, storage identical); backend image built and smoke-tested (refuses dev config in production, non-root, `rls_enforced: true`) |
| 2026-10-15 | 8 | pytest **568 passed** (new `test_branding.py`: WCAG contrast math, hue-preserving fit, brand-as-fill, note-key conflict, text accent ≥ 4.5:1 on all 4 light + 4 dark surfaces for 9 brand colours incl. yellow and pale cyan, monochrome logos fall back, type mood from industry; logo upload re-encoded (appended `<script>` bytes gone, ≤ 512 px), SVG/GIF/garbage/broken/4200-px/> 1 MB refused, JPEG accepted; overrides validated; viewer reads but can't change; rival isolated; export carries the logo; removal falls back) + migration 0008 up/down/up, `alembic check` clean, ruff clean; lint/typecheck/build clean; impeccable detector: no findings; Playwright **9/9** with axe AA on every visited page incl. new `phase8.spec.ts` (yellow-logo food distributor: palette extracted, accent derived, all 5 contrast checks pass, logo in the rail, runtime accent applied, note key opens its note, approval focus, owner picks colour + Market mood → headings render in Bricolage Grotesque, status colours unchanged, mobile Control Center + readiness, landing + login); finish review: two fix rounds — round 1 resolved 6/8, round 2 resolved fix 4 and the 3 regressions; open: runs table below the Control Center's first viewport at 1280×720, daily-report figure baselines when a label wraps, a half-empty last row on the daily report |

## Known limitations (honest list)
- **No live AI calls yet.** LLM = labelled dev adapter; embeddings = lexical hash adapter. Phase 3 model paths (rule
  extraction, job-description refinement) are tested with a fake client only. In dev, rule extraction lists rule-like
  sentences verbatim and generation returns the catalog template fitted to the company — both labelled. Ask the user
  before enabling `ABOS_LLM_PROVIDER=anthropic` (billed). After switching embeddings: reprocess all documents and
  re-tune `ABOS_RETRIEVAL_MIN_VECTOR_SCORE` with the eval suite (ADR-016).
- Real execution covers the platform's own records only: invoices, payments, expenses, drafts, execution records and
  objectives. Every other catalog tool (CRM, tickets, inventory, HR, campaigns, …) is "not connected", so those
  agents' tasks end `needs_review` with missing evidence. No external integration or OAuth connector exists yet.
- In dev, runs are planned by deterministic playbooks (labelled) — they prove governance, tools, evidence and
  validation, not model judgement. Only Finance (3 tasks) and Executive (briefing, KPI review, requests) have
  playbooks; other tasks use a generic gather-and-report playbook. The model planner (step-wise) is tested with a fake
  client only. Expense "categorisation" in dev is a labelled keyword rule.
- `reminder.send` and notification emails go through the mail adapter: dev outbox = stored, never delivered. SMTP
  reconciliation (outbox `sent`/`failed` → reconciliation / delivery status) is tested with simulated outbox states
  only. SMS has only the labelled dev provider (refused in production); no real SMS provider is implemented.
- Daily reports and the Control Center still compute in Python over the period's rows (the Control Center caps runs
  at 5000). Their *query counts* are constant (Phase 7 test), but very large tenants should move the counts into SQL.
  Catalog business KPIs have no measurement source, so reports list them as unmeasured.
- One unexplained failure of `test_daily_report_is_built_from_execution_records` was seen once (the resumed run was
  missing from "completed"); it passed in 10+ reruns since — watch for a timing flake.
- Task-level `retry_backoff_minutes` is not applied: transient tool faults retry immediately within the limits; a
  failed run is not rescheduled later. Schedule occurrences missed for more than 15 minutes (scheduler down) are not
  replayed. Tool timeouts are enforced for database work (`statement_timeout`); the mail handoff is transactional.
- KPI progress can't be computed: objectives have targets but no recorded measurements.
- Simulations use sandbox fixtures; the readiness model planner is single-shot and tested with a fake client only.
- Some agents can't exercise every category (e.g. HR has no drafting or external tool → no duplicate/approval-required
  scenarios); per-agent coverage is shown in the simulation center.
- Rule conflict detection only compares money thresholds; conflicting non-numeric statements need the model path or a
  reviewer. Task ↔ rule linking (policy refs) is keyword overlap; the CEO can edit refs only via the API today (the
  editor keeps them but has no picker).
- Recommendation budget check works only for USD budgets (no exchange rates are invented).
- OCR: Tesseract is not installed; scanned pages are reported, not read.
- S3 storage adapter untested (the backend image installs boto3); local storage only. No malware scanning
  (`scan_status = not_scanned`).
- URL import over https has a small DNS-rebinding window (documented in `knowledge/fetch.py`); production should route
  egress through a proxy that blocks private ranges.
- No reranker, no query rewriting (both optional in the spec).
- Email is the `dev_outbox` adapter; member invitations need an existing account; no MFA/SSO.
- **CI has never run**: `.github/workflows/ci.yml` is written (its YAML parses, the prod compose file validates) but
  the repo has no commits or remote. Locally verified instead: ruff, pytest, migrations, lint/typecheck/build,
  Playwright, backend image build + smoke test. **The web image (`frontend/Dockerfile`) is unverified**: its build
  sat in `npm ci` for 50 minutes on this machine (known-slow npm) and was stopped; CI's `images` job is the first real
  check. The standalone output it packages is verified (`next build` with `output: "standalone"` succeeds).
- Sentry reporter: implemented behind `ABOS_ERROR_REPORTER=sentry`, **not verified against a live project**; the
  default `log` reporter is what's tested. Metrics are scraped from one API process for HTTP counters (per-process,
  as usual for Prometheus) and from the DB for background work.
- Exports are built in memory (fine at MVP volumes). Restoring a backup older than a workspace deletion brings that
  workspace back — replay `organization_deletions` after a restore (manual step, docs/OPERATIONS.md). Audit events of
  deleted workspaces are kept, detached, with no automatic purge.
- "Needs re-testing" runs the readiness check per tested agent (bounded: one live instance per catalog definition).

## Session log
- **2026-10-14 (1)** — Phase 0 + Phase 1 (see verification record). Fixed during verification: unique violation at
  flush → 500 (now 409); sidebar logo contrast; self-remove button.
- **2026-10-14 (2)** — Phase 2. Backend: `storage`, `llm` (gateway, embeddings, usage ledger), `jobs` (Celery +
  durable job_runs + sweeper), `knowledge` (parsing, OCR adapter, chunking/classification, safety/redaction, SSRF-safe
  fetch, ingest pipeline, documents service, hybrid retrieval, verified answers, evals, interview); migration 0002
  (10 tenant tables with RLS, insert-only ledgers). Frontend: documents library (drag-drop upload with progress, URL
  import, polling), document detail/review, Ask, evaluation, business interview. Bugs found and fixed by tests:
  migration 0002's blanket GRANT re-enabled UPDATE/DELETE on audit_events (removed; rule added to CLAUDE.md);
  DOCX Title nesting; "S1" source labels read as unsupported figures; irrelevant zero-score vector hits shown as
  sources (relevance threshold, ADR-016); `subtle` text token 4.46:1 contrast (darkened).
- **2026-10-14 (3)** — Phase 3. Backend: `agents` (policy vocabulary, frozen catalog v1, models, schemas, lifecycle,
  schedule, validation, recommendation, design/generation, service incl. execution guard, router) and `governance`
  (business rules extraction/review/policy version, approvals ledger, router); migration 0003 (6 tenant tables with RLS,
  catalog seed, catalog read-only, approvals insert-only). Frontend: agent directory, catalog, recommended/custom team,
  agent profile with 8 tabs, configuration editor, business rules, approval inbox + approval summary, overview workforce
  card, accessible Tabs primitive. ADR-017…021, `docs/AGENTS.md`. Found and fixed during verification: test cleanup
  wiped the migration-seeded catalog (now skipped); dev rule extractor missed declarative facts and glued heading paths
  onto statements after redaction; `ApiError.fieldErrors` crashed on non-field error details; templates contradicted
  their own observe-only level (writes now denied); in-text links lacked underlines (axe link-in-text-block); test
  cleanup switched TRUNCATE → DELETE (suite 276–620 s → 66 s on Docker Desktop).
- **2026-10-14 (4)** — Phase 4. Backend: `simulation` (models, sandbox + governance dispatcher, validated invoice
  checks, scenario library for all 8 agents, runtime with gateway planner, deterministic evaluation + thresholds +
  failure analysis, service: library sync, custom scenarios, background run job, readiness gate, activate/widen/pause/
  resume, rollback, apply suggestion; router); migration 0004 (3 tenant tables with RLS, deployment stage);
  `execution_allowed` gains activation + observation-scope checks; sweeper marks timed-out runs. Frontend: readiness &
  deployment page, run detail with traces and apply-suggestion, simulation center with library + custom scenarios,
  agent "Test results" tab, version restore, approval subjects labelled. ADR-022…024, `docs/SIMULATION.md`. Found and
  fixed during verification: probe tools missing a registry flag; synthetic search hits missing a field; success colour
  4.37:1 on its tint (darkened to pass 4.5:1); the Postgres container had stopped after the session resumed
  (restarted with `docker compose up -d`).
- **2026-10-15 (5)** — Phase 5. Backend: `governance/dispatch.py` (decision path shared with the sandbox), `tools`
  (code-defined registry, handlers, write-once ledger), `business` (invoices, lines, payments, expenses, drafts,
  validated calculations), `orchestration` (state machine, runs, planner with playbooks + model path, service:
  claim/lock/guard/dispatch/approve/idempotency/retries/validator/delegation, events, scheduler, router),
  `governance/actions.py` (parameter-bound approvals); migration 0005 (8 tenant tables with RLS, insert-only lines and
  payments, write-once trigger on `tool_executions`, no DELETE on runs); permissions `records.read/manage`; Celery
  beat `abos.schedule_tick`, `python -m abos.jobs tick`. Frontend: tasks (run now, ask an agent, runs), run detail
  (result, checks, delegated runs, evidence ledger, approvals), action approvals in the inbox, business records
  (invoice form, payments, expenses, drafts), agent "Activity history" tab. ADR-025…028, `docs/EXECUTION.md`. Found and
  fixed during verification: SQLAlchemy fires `after_commit` on SAVEPOINT release, so job dispatch and SMTP delivery
  could run before the real commit (both hooks now skip nested transactions — it broke delegation); the Phase 4
  widen check compared DB time with host time (Docker clock ~0.2 s behind → flaky test; `activated_at` now uses DB
  time); a second review re-reminded an invoice reminded minutes earlier (one reminder per invoice per 7 days); a
  duplicate of an unverified side effect was counted as done (now `unverified`); a resumed run didn't reconcile its
  own `started` rows (now `unverified`, not repeated).
- **2026-10-15 (6)** — Phase 6. Backend: `reporting` (daily reports + evidence index, Control Center), `notifications`
  (models, channels — email via the mailer, SMS adapter interface with a dev provider —, service: recipients by
  permission, preferences, limits, retries, digests, email reconciliation; router), `usage` (summaries, budgets),
  `tools/reconcile.py`; emit points in action requests, `escalate`, run outcomes, budgets; scheduler tick now also
  reconciles, retries deliveries, finalises reports and sends digests; budgets enforced at claim; migration 0006
  (6 tenant tables with RLS, insert-only reconciliations); settings `sms_provider`, delivery limits, max attempts
  (production refuses the dev SMS provider). Frontend: Control Center (filters), daily reports list + report, notification
  center (inbox, preferences, delivery log) + unread badge, usage & costs, agent "Reports" and "Performance" tabs;
  shared `e2e/helpers.ts`. ADR-029…031, `docs/REPORTING.md`. Found and fixed during verification: per-day usage
  grouping failed in Postgres (each `timezone()` call bound its own parameter) — now aggregated in Python by local day;
  the preferences form was keyed by its data, so saving remounted it and hid the confirmation. Infra: Docker Desktop
  had stopped after a restart (started; `docker compose up -d postgres redis`).
- **2026-10-15 (7)** — Phase 7. Backend: `privacy` (retention settings + housekeeping purges, owner-only export job,
  scheduled workspace deletion with grace period on the owner DB path, `organization_deletions` record),
  `core/metrics.py` (Prometheus text, DB-derived background gauges), error-reporting sink with optional Sentry adapter,
  log context (request/job/run ids stamped at record creation), `ai_work` rate limit on 13 costly routes, usage
  aggregation in SQL (was one query per agent + every usage row in Python), `needs_retest` in the Control Center,
  `python -m abos.jobs housekeeping` + hourly beat task; migration 0007 (columns on `organizations`, `org_exports` with
  RLS, `organization_deletions` revoked from the app role, 3 `(organization_id, created_at)` indexes). Frontend:
  Settings → Data & privacy (retention, exports with download, schedule/cancel deletion), deletion banner in the shell,
  Control Center "Needs re-testing", shared `lib/download.ts` and `useAction`. Infra: backend/frontend Dockerfiles,
  `infra/deploy/compose.prod.yml`, `infra/backup/backup.sh|restore.sh`, `.github/workflows/ci.yml`. Docs:
  `SECURITY.md`, `OPERATIONS.md`, `DEPLOYMENT.md`, ADR-032…034. Found and fixed during review/verification: the DB URL
  (with password) was visible in `repr(Settings)`; no rate limits on model/worker-heavy routes; usage endpoint N+1; a
  platform table named its column `organization_id` and was swept into "tenant tables" (renamed); GNU tar can't write
  to `C:/` paths (archive via stdout); a leftover uvicorn child held port 8470 after restarts. Learned: editing an
  active agent's configuration already takes it out of service (`configuring`) until re-approved and re-tested.
- **2026-10-15 (8)** — Phase 8 (design). Product context interview → `PRODUCT.md` (SMBs, Philippines first; name fixed;
  tenants change accent + logo + type mood only). Direction round on the impeccable decision page / fallback question:
  user chose **The Annual Report** (seed 2d3b5e2a; contract in `.impeccable/surfaces/frontend-src-app-app.md`).
  Backend: `branding` module (logo sniffing + re-encode with Pillow, palette, `colors.py` WCAG derivation, `moods.py`,
  service/router at `/api/v1/org/branding`), migration 0008 (`workspace_branding`, RLS), deletion/export cover logos.
  Frontend: token layer rebuilt (`globals.css`), five type moods (`lib/fonts.ts`, loaded only when used), runtime tenant
  theming (`lib/branding.tsx`), new primitives (`components/ui/report.tsx`: Figures/Notes/ReportSection; Capacity;
  glyph+word badges; ink-ruled tables), new mark and rail, Settings → Branding, Control Center and daily report rebuilt
  around figures with notes, approval focus, readiness next step, landing + auth redesigned; `DESIGN.md` +
  `.impeccable/design.json` written by the documenter. Found and fixed: editor remount dropped the upload confirmation
  (action state lifted); accent fitted only to the page ground failed on tinted surfaces (now fitted to the darkest /
  lightest surface); the note flash tinted text backgrounds below AA (now an outline); a `<dl>` held a non-dt/dd child;
  uvicorn's 5 s keep-alive caused ECONNRESET 500s through Next's proxy (now 75 s, Dockerfile + docs); yellow logos
  shipped as olive (brand now fills buttons when it carries text). Open after the review budget: Control Center runs
  table below the 1280×720 fold (notes column height), daily-report figure baselines when a label wraps, half-empty
  last row on the daily report; documenter also noted older screens with pre-Phase-8 uppercase labels and one
  `shadow-sm` (agents/team), and `#c9a24a` hard-coded in two components instead of a token.
