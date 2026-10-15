# Architecture decision records

Short, numbered, never rewritten — supersede with a new ADR instead.

## ADR-001 — Modular monolith
FastAPI service + Next.js app + one Postgres. Modules own their tables and expose service functions. Splitting
later is possible along module lines; distributing now would add network failure modes before there is load.

## ADR-002 — Reuse the GSM AI Technician foundation
`~/projects/gsm-ai-technician` already has a verified FastAPI/Postgres/RLS/session-auth/audit stack and Next 16 UI
primitives with the same target stack. Those modules are adapted (renamed `gsm` → `abos`, `GSM_` → `ABOS_`), not
re-invented. Domain modules (repair cases, firmware) are not copied. MFA is deliberately left out of Phase 1 (Phase 7).

## ADR-003 — Two tenancy layers: app authorization + Postgres RLS
App layer: `require_org_member` verifies the `X-Org-Id` membership server-side and every service filters by org.
DB layer: the API runs as `abos_app` (NOLOGIN, no BYPASSRLS; the login user `SET ROLE`s into it); tenant tables have
`ENABLE ROW LEVEL SECURITY` + policy `organization_id = current_setting('app.org_id')` or `app.system_scope = 'on'`.
Settings are transaction-local and re-applied after each BEGIN, so pooled connections never leak a tenant.
`tests/test_rls.py` fails when a table with `organization_id` lacks a policy.

## ADR-004 — Permissions, not roles, in code
Roles: owner, admin, manager, member, viewer. Routers depend on `require_org_permission("<perm>")`; the only map is
`identity/permissions.py`. Business title (CEO, CFO…) is `organization_memberships.job_title` and grants nothing.
Agent-level permission scopes (Phase 3) are a separate system and never inherit a human's role.

## ADR-005 — Relational company profile, JSONB only for flexible shapes
The profile has a 1:1 `company_profiles` row with scalar columns plus typed child tables (locations, departments,
job roles, offerings, objectives, processes, software, challenges). JSONB only for the weekly operating schedule,
holidays and notification preferences, each validated by a Pydantic schema before storage.

## ADR-006 — Missing information is computed, not stored
`GET /company/completeness` derives which onboarding sections are empty or thin from the live rows, so it can't
drift. Nothing in the wizard is mandatory beyond company name; skipped sections show as "missing" with a reason,
and later phases (interview, agent configuration) consume the same list to ask for context.

## ADR-007 — shadcn-style components, owned locally
UI primitives live in `src/components/ui` (cva + tailwind-merge), shadcn's copy-in model, without the CLI or Radix
until a primitive needs it (dialogs/tabs get accessible local implementations or Radix when justified).

## ADR-008 — Celery + Redis transport, Postgres holds durable state
Redis is the broker (spec §5). Correctness never depends on a Redis message surviving: every job's state lives in
Postgres (document status, `job_runs`), and a sweeper re-enqueues jobs stuck past their timeout. On Windows the
worker runs `--pool=solo`. Tests execute tasks eagerly.

## ADR-009 — API versioning under /api/v1
All business endpoints live under `/api/v1`. Health stays at `/api/health*` (unversioned, infrastructure).
CSRF guard: unsafe methods need `X-Requested-With: abos`.

## ADR-011 — Private object storage behind the API
Originals live in object storage (`local` dir in dev, S3-compatible in prod) under server-built keys
`{org}/{doc}/v{n}`; never public. Downloads go through `GET /documents/{id}/download` after the same tenant +
access-level check as everything else (no signed URLs yet — simpler, and files are small). SHA-256 per version is
re-verified before parsing. Malware scanning: not implemented; `scan_status = not_scanned` is recorded honestly.

## ADR-012 — LLM gateway with labelled dev adapters
One module (`abos.llm.gateway`) talks to providers. Each task passes a deterministic `dev` function used when
`ABOS_LLM_PROVIDER=dev`; its output is always labelled "Development adapter" in the API and UI. The Claude adapter
uses `claude-opus-5-5`, JSON-schema structured output, explicit effort (default medium), and server-side refusal
fallbacks (`fallbacks: "default"`). Every call — ok, error, refusal — is written to `model_usage` in its own
transaction. Embeddings: `hash` (dev, lexical), `voyage`, `openai`-compatible; fixed at 1024 dimensions because
the pgvector column and HNSW index need a fixed size. Production refuses dev adapters.

## ADR-013 — Review gate: only `indexed` documents are retrievable
SPEC asks for a review screen and for agents to use only approved knowledge. Rather than a separate "approval"
flag, the status machine is the gate: processing ends in `awaiting_review`; approval moves to `indexed`. Retrieval
SQL filters on `status = 'indexed'`, so an unreviewed, rejected, superseded or archived document can never reach a
model. A new version or reprocess re-enters review. `supersedes_document_id` retires the outdated policy on approval.

## ADR-014 — OCR is optional and never faked
Tesseract is an external binary not present on this machine. Without it, scanned pages produce an explicit warning,
and a fully scanned document fails with `no_text_ocr_unavailable` (retryable once OCR is installed).

## ADR-015 — Deterministic answer verification, not an LLM judge
Grounding is enforced after generation: citations must reference provided source ids and quote them verbatim
(whitespace/case-insensitive), and figures in the answer must appear in the sources. Failures downgrade the answer
to `unsupported`. Instruction-like sentences in documents are flagged at ingestion and redacted before any model
sees them. RAG evals grade with the same deterministic checks.

## ADR-016 — Relevance threshold instead of "top-k always"
Nearest-neighbour search always returns k results. A vector-only candidate must reach cosine ≥
`ABOS_RETRIEVAL_MIN_VECTOR_SCORE` (0.25) to count; keyword matches always count. If nothing qualifies the answer
is "insufficient evidence" and no model is called. The threshold is provider-dependent — re-tune it (with the eval
suite) when switching to real embeddings.

## ADR-017 — Business rules: explicit statuses, verified sources, nothing enforced unconfirmed
SPEC step 4 asks to distinguish facts, interpretations, confirmed rules, open questions and conflicts, and never to
turn ambiguous text into enforced rules. One `business_rules` table with a status per item (fact · proposed ·
unresolved · conflicting · confirmed · rejected) and a `source_type` (document · interview · profile · manual). Only
`confirmed` rules (and not stale ones) feed agent configuration. Document items are verified like answers (ADR-015):
verbatim quote from a provided source, every figure present in the quote, else dropped. Money thresholds are parsed
from the quote deterministically (SPEC §2). Conflicts are detected by rule (same currency, different amount, different
source, ≥ 50 % subject-word overlap) rather than asked of a model. Staleness (cited document no longer indexed) is
computed on read, like completeness (ADR-006). A separate `policies` / `policy_versions` table was not needed: the
policy version bound into approvals is derived from the confirmed rule set.

## ADR-018 — Versioned configuration: JSON document + relational tasks, hash-bound approvals
The agent configuration is one Pydantic-validated JSONB document per version; tasks and dependencies are rows of that
version (Phase 5 schedules them). Permission scopes and knowledge access live inside the document instead of separate
`agent_permissions` / `agent_knowledge_access` tables: they are versioned and hashed together with everything else the
CEO approves, and the scope vocabulary is code-defined (ADR-019). A draft is edited in place; submitted / approved /
rejected versions are frozen and an edit creates the next version. `config_hash` = sha256 of canonical config + tasks.
A decision must carry the hash the approver reviewed, which must equal the stored hash and one re-computed from the rows;
the insert-only `approvals` row records it with the policy version and the authorised scope. The execution guard
re-computes the hash again, so changes behind the API stop execution.

## ADR-019 — Agent permission scopes and ceilings are code-defined
Like `identity/permissions.py` (ADR-004), `agents/policy.py` is the single map of scopes, risk levels, platform
ceilings, default modes, events and operating modes. Two ceilings apply: platform (approving transactions is never
delegated to an AI; critical scopes never run unattended) and per catalog definition (e.g. Finance never executes
payments). Exceeding either is a validation error, enforced on submit and again on approval. Templates start at
min(default, ceilings) and observe-only agents start with all write scopes denied. Agent scopes never inherit a
human's role.

## ADR-020 — Deterministic team recommendation
The recommended team is computed from weighted profile signals declared on each catalog definition, with a reason per
point, threshold 2, the Executive agent added once two others qualify, and budget trimming only when the company budget
is in USD (no invented exchange rates). Reproducible, explainable, testable and free; a model adds little here and
would make "why this agent?" unanswerable.

## ADR-021 — The catalog is migration-seeded platform data
`agent_definitions` has no tenant and is read-only to `abos_app` (INSERT/UPDATE/DELETE revoked). Catalog content is a
frozen Python module imported by the migration that seeds it; new versions are new modules + migrations, so a
re-run of old migrations always reproduces the same catalog. The test cleanup skips migration-seeded tables
(`tests/conftest.SEEDED_BY_MIGRATIONS`).

## ADR-022 — Simulation = sandboxed tools behind the real governance dispatcher; scripted plans in dev
SPEC step 6 requires scenario execution before Phase 5 has real tools, and no billed model calls may run unasked.
Scenarios run against fixture-backed sandbox tools, but every call goes through the dispatcher Phase 5 will reuse
(authorisation, scope modes, deployment stage, confirmed money thresholds, approval flags, idempotency, retries,
tenant isolation). The planner goes through the LLM gateway: a real model plans when configured; the dev adapter
returns the scenario's scripted attempts — what a naive or compromised agent would try — and is labelled. A dev run
therefore proves what the platform and the configuration allow, hold or refuse, not the model's judgement. Grading is
deterministic assertions only; mandatory security checks override scores; thresholds are per agent type.

## ADR-023 — Readiness is computed; activation is staged and recorded like an approval
Readiness is derived on read (like completeness, ADR-006): approved current configuration + passing run of that exact
hash under the current policy version + full required-scenario coverage. Any material change (new configuration
version, new confirmed rules, new library version) therefore needs regression testing automatically. Activation and
widening are owner decisions stored as `approvals` rows (subject types `activation`, `deployment_stage`) bound to the
config hash and the run. Activation always starts in observation (read + drafts); widening needs a passing run after
activation. Pause is immediate; resume re-checks readiness.

## ADR-024 — Test-driven suggestions may only narrow
Failure analysis proposes concrete configuration changes, but only narrowing ones (deny, require approval, task
approval, escalation lines, retries) can be applied automatically, and each creates a new draft version that goes
through approval and testing again. Anything that widens access is shown as a manual step — the platform never grants
permissions because a test (or an agent) suggested it (SPEC §4). Rollback restores a previously approved version as
a new draft under the same rule.

## ADR-025 — One dispatcher for simulation and execution; a code-defined tool registry
The governance decision (authorised tool, scope mode, deployment stage, confirmed money thresholds, approval flags)
lives in `governance/dispatch.py` and is called by both the simulation sandbox and real execution, so a passing
readiness run tests exactly the code that governs live work. The registry is code (`tools/registry.py`), not a
`tool_definitions` table as first sketched in ARCHITECTURE: a tool is a handler plus its schemas and policies, and a
DB row can't add a handler — storing schemas separately would only allow drift. `REGISTRY_VERSION` is recorded on every
ledger row. Catalog tools without an integration are registered as "not connected" and refused, never simulated.

## ADR-026 — Action approvals are bound to the exact resolved parameters
A held call raises an `action_requests` row with the parameters the action would really use (a send resolves the
draft into recipient, subject and full text) and `params_hash = sha256(tool, parameters, instance, config hash,
policy version)`. The decision must carry that hash and is also written to the insert-only `approvals` ledger
(`tool_action`). On resume the parameters are resolved again; only an approved request with the identical hash runs,
once. A changed draft, a newly confirmed rule or a new configuration supersedes the approval and raises a new request.
External sends (`reminder.send`) need approval on every call in this release, whatever the configuration says; an
approved action may run in the observation stage (`execution_allowed(..., approved_action=True)`).

## ADR-027 — Step-wise orchestrator, playbooks in dev, Postgres for locks, deterministic validation
The orchestrator asks the planner for one action at a time (bounded to 25 steps) so plans adapt to tool results; a
real model plans through the gateway, the dev adapter runs a deterministic per-task playbook and the run is labelled.
No LangGraph: the state machine is small and explicit (`orchestration/state.py`) and each step's state is the ledger,
which makes crash recovery a re-read. Locking and idempotency use Postgres instead of Redis locks: claiming locks the
run and agent rows (overlap and daily-limit checks), and unique keys on `workflow_runs.idempotency_key` and
`tool_executions.idempotency_key` make duplicate triggers and repeated side effects impossible across workers — the
state is already durable there (ADR-008). Non-transactional side effects write a `started` row first; anything left
`started` becomes `unverified`, never success. Delegation is one level (Executive → others) through stored results,
not agent-to-agent conversation. Completion is checked deterministically, including "every figure appears in a tool
result" — no model judges a model (as ADR-015).

## ADR-028 — Business records: computed money, insert-only corrections
Invoice totals are computed from lines (`Decimal`, half-up to cents) and balances from payments at read time; an
imported stated total is kept separately so a mismatch is a discrepancy to escalate, not a number to trust. Payments
are recorded under a row lock, never above the balance, with a unique bank reference per invoice; lines and payments
are insert-only for the app role. Agents get read tools and drafts only. One payment reminder per invoice per 7 days
is a platform rule (tool validation + playbook).

## ADR-029 — Daily reports are a deterministic projection of the execution records
SPEC step 8 forbids reports from a model's recollection, so no model writes them: `reporting.build` projects one
company-local day of runs, ledger rows, action requests, reconciliations, usage and the approved schedule into the 15
SPEC sections, each item carrying its ids (indexed in `report_evidence`). A report is a cached projection, not
evidence itself: it can be rebuilt (version + 1), e.g. after a late approval; `final` records whether the day had
ended. Unknown outcomes are settled by insert-only `execution_reconciliations` rows rather than by rewriting the
write-once ledger. Business KPIs from the catalog are listed as unmeasured until a measurement source exists — only
platform metrics (completion, SLA, actions completed vs attempted) are computed.

## ADR-030 — Notifications: recipients by permission, deliveries as records, providers behind adapters
Who is told is decided by the permission that makes the event actionable (`approval.decide`, `task.manage`,
`usage.read`, `report.read`), never by role or title. In-app rows always; email and SMS are `notification_deliveries`
rows sent by background jobs after commit, with status, provider, attempts and error, bounded exponential retries,
per-user delivery limits and a once-a-day digest in the company time zone. Email reuses the mailer (its outbox status
is reconciled into the delivery); SMS is an adapter interface with a labelled dev provider, refused in production —
no messaging provider is hard-coded and no real SMS provider is claimed.

## ADR-031 — Agent budgets are enforced at claim time from the usage ledger
`limits.monthly_budget_usd` is part of the approved configuration, so the orchestrator enforces it: month-to-date
spend (company time zone) from `model_usage` at or above the budget skips the run with the reason and notifies
`usage.read` holders once a month. Costs are the gateway's estimates; the provider invoice is authoritative. Dev calls
cost nothing and are labelled. The company budget is only compared in USD (no invented exchange rates, as ADR-020).

## ADR-032 — Metrics without a client library; background counts come from the database
`GET /api/metrics` (Prometheus text, bearer token, off when no token is set) renders in-process request counters and
latency histograms for the API process, plus gauges computed from durable rows at scrape time (jobs by kind/status,
queue lag, runs, tool executions, deliveries, documents, pending approvals), cached 15 s. Workers and beat are
separate processes, so counting their work from the database is the only way every replica reports the same numbers;
it also avoids Prometheus multiprocess mode and a dependency. Labels are route templates and statuses — never ids,
tenant names or user input. Unhandled errors (API and jobs) go through one `report_exception` sink: JSON log line with
request/job correlation ids, a counter, and optional reporters (Sentry adapter, not live-verified).

## ADR-033 — Data controls: scheduled workspace deletion on an owner path; export as a job; bounded retention
Deleting a workspace must remove write-once evidence and insert-only ledgers that the app role can never delete, so
deletion runs in housekeeping on a separate *owner* connection (`ABOS_MAINTENANCE_DATABASE_URL`, worker only, never
the API): one transaction deletes the `organizations` row and FK cascades remove every tenant row; then files are
deleted. Owners confirm with the exact workspace name and their password; deletion waits a grace period (default
72 h, every owner emailed, any owner can cancel). Audit events survive with the workspace link nulled (the append-only
trigger permits exactly that) as the platform's security record; an `organization_deletions` row (no tenant data,
revoked from the app role) proves the deletion. Exports are owner-only jobs that read through the RLS-bound session
and also filter by org, skip derived search data, include original files, and expire. Retention windows are
per-workspace with floors (30 days; 90 for reports); evidence, ledgers, business records, usage and audit are kept
while the workspace exists.

## ADR-034 — Every route is checked by enumeration
`tests/test_security_surface.py` walks the app's routes: authentication unless allow-listed public, a named permission
on every workspace route (only `GET /org` is member-only), no data change behind a `.read` permission except
caller-owned rows, a rate limit on every route that starts model or worker work (`ai_work`: per user and per
workspace), and live calls proving anonymous → 401, non-member → 403, viewer → 403 for every route above viewer
level. New routes are covered automatically; allow-lists must name existing routes.

## ADR-035 — Design: "The Annual Report" identity; tenants brand the accent, logo and type mood only
Chosen with the user from a direction round (PRODUCT.md, `.impeccable/surfaces/frontend-src-app-app.md`): agent
output is set like an audited report — deep green rail, paper ground, ink rules, grotesk figures at report scale whose
superscript note keys open "Notes" that say how each figure was counted and link to its records. Workspace branding
is server-side: the logo is sniffed, size/pixel-limited, re-encoded to PNG (SVG refused) and its palette extracted;
the most prominent chromatic colour becomes the brand. The brand fills buttons whenever ink or white text reaches
4.5:1 on it; links and focus use a hue-preserving lightness fit that reaches 4.5:1 on every surface of each theme; the
rail marker needs 3:1 on the green; brass-like accents switch note keys to ink. Only `--brand-*` and `--mood-*` CSS
variables change at runtime — status colours, layout and chrome are the platform's in every workspace. Type moods are
a curated set of five pairings matched from the industry (owner can override); fonts load only when used.

## ADR-010 — Ports
Postgres 55470 (dbs `abos`, `abos_test`), Redis 56470, API 8470, web 3470. Other local stacks occupy
5432, 6379, 8000, 15433, 55450, 55460, 56390, 8460, 3460.
