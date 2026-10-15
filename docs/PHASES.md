# Phased implementation checklist

Work strictly one phase at a time (SPEC §10). A box is ticked only when the feature works end to end **and** is
covered by a passing test or a recorded verification (see STATUS.md session log). Never tick on "code written".

Legend: `[x]` done & verified · `[~]` partial (see note) · `[ ]` not started

## MVP boundary (SPEC §12)

The MVP is the single vertical slice: register → profile → upload SOP → RAG index → hire Finance agent → generated
job + tasks → CEO approval → simulation passes → activation (observation/draft mode) → authorized read-only finance
task with tool evidence → daily report traced to evidence → delivered via notification → CEO can pause/edit/re-test.
Breadth (all 8 agents fully operational, many integrations) comes **after** the slice works.

Out of MVP (later): real external integrations beyond 1–2 adapters, OAuth connectors, SMS delivery provider, billing,
SSO/MFA, multi-region, fine-tuning.

---

## Phase 0 — Inspection & architecture
- [x] Inspect workspace (empty repo; reuse verified patterns from ~/projects/gsm-ai-technician — ADR-002)
- [x] Architecture document (`ARCHITECTURE.md`)
- [x] MVP boundaries + phased checklist (this file)
- [x] Security-critical decisions & entities (`ARCHITECTURE.md` §3–4, `DECISIONS.md`)
- [x] Initial schema + API contracts (`ARCHITECTURE.md` §4–5)
- [x] Dev/test/env configuration (docker-compose, `.env.example`, CLAUDE.md commands)

## Phase 1 — Working SaaS foundation
- [x] Postgres + pgvector + Redis via docker compose; Alembic migrations; `abos_app` RLS role
- [x] Auth: register, login, logout, me, email verification (dev outbox), password reset, change password, sessions
- [x] Organization creation (on register + additional workspaces); first user = **owner**; job title separate
- [x] Org-scoped authorization (`require_org_member` / permissions) + RLS policies on every tenant table
- [x] Members: add, change role/title, remove (last-owner guard, only owners mint owners)
- [x] Company profile (all SPEC step-1 fields) + collections (locations, departments, job roles, offerings,
      objectives/KPIs, processes, software, challenges); missing-info / completeness endpoint; skip sections
- [x] Audit event infrastructure (append-only trigger + revoked grants, API + page)
- [x] Rate limits on auth endpoints; security headers; CSRF header; structured JSON logging
- [x] Frontend: landing, sign-up, login, password recovery, verify email, app shell, onboarding wizard
      (9 steps, skip-able, missing info flagged), dashboard (real data only), company profile, settings
      (workspace, members, account, sessions, new workspace), audit log
- [x] Tests: auth, tenant isolation (API + RLS), permissions, profile persistence, audit immutability (42 tests)
- [x] Verified: pytest green, ruff clean, `npm run lint/typecheck/build` clean, Playwright browser E2E + axe
      (API-level journey is covered by pytest; the AI-guided interview moved to Phase 2 — needs the LLM gateway)

## Phase 2 — Business knowledge & RAG
- [x] Object storage adapter (local dev verified; S3 adapter written, **not live-tested**), private, authenticated download
- [x] Upload validation (byte sniffing, extension agreement, size limits), document + version records, all 8 statuses
- [x] Parsers: PDF, DOCX, XLSX, CSV, TXT/MD, URL/HTML (SSRF-guarded, per-hop public-IP check)
- [~] OCR: adapter + honest `ocr_unavailable` / `no_text_ocr_unavailable` handling; Tesseract not installed, so actual
      OCR is **not verified**
- [x] Rule-based classification (reviewer override), structure-aware chunking (headings, tables w/ repeated header),
      chunk metadata (page/section/version; access & status joined from the document)
- [x] Celery worker + Redis (live-verified, `--pool=solo`); durable `job_runs` with step log; bounded retries;
      SKIP LOCKED claim; sweeper for lost/stuck jobs
- [x] LLM gateway (dev labelled; Claude adapter request shape unit-tested, **no live call made**) + embeddings
      (hash dev; voyage/openai adapters **not live-tested**); `model_usage` ledger incl. errors/refusals
- [x] Hybrid retrieval (pgvector HNSW + FTS, RRF), org/status/version/access filters in SQL, relevance threshold
- [x] Ask: grounded JSON answers, deterministic citation + figure verification, insufficient/conflicting disclosed,
      instruction-like text redacted, every answer stored as evidence
- [x] Knowledge review screen (summary, warnings, classification, access, effective date, supersedes, approve/reject)
- [x] AI-guided business interview (rule follow-ups from gaps + content; model questions when a real LLM is set)
- [x] RAG evaluation UI + API: cases, runs, hit rate / MRR / precision, citation validity, unsupported claims,
      security checks; outdated / conflicting / inaccessible / missing / injection scenarios all pass (dev adapters)
- [x] Demo: SOP uploaded in the browser → processed by the real worker → reviewed → answered with a verified citation

## Phase 3 — Agent catalog & configuration
- [x] Agent definitions A–H seeded in DB (versioned, frozen catalog module, read-only to the app role), catalog API + page
- [x] Recommended team (deterministic rules over profile/documents/budget, reasons shown) and custom team
- [x] Agent instances + lifecycle state machine (available → … → retired) enforced server-side; approved-config
      invariant for testing/ready/active/paused; execution guard for Phase 5 tools (activation/pause endpoints: Phase 4)
- [x] Business rule extraction: facts / proposed interpretations / confirmed / unresolved / conflicting, verified
      quotes, deterministic thresholds + conflicts, stale detection (dev adapter verified; model path tested with a
      fake client only — **no live model call**)
- [x] Job description generation (structured, validated config) + proposed tasks (trigger, schedule, inputs, outputs,
      criteria, dependencies, SLA, policy refs, permissions, approval, retry) — dev adapter = labelled template; model
      refinement tested with a fake client only
- [x] Operating modes (24/7, business hours, scheduled, event-driven, on-demand); monitoring vs execution windows;
      schedule calculations in company time zone with hours and holidays
- [x] Permission scopes + risk levels + platform/definition ceilings; configuration versioning with hashes
- [x] CEO review & approval screen; approvals recorded (user, role, decision, time, version, hash, policy version, scope)

## Phase 4 — Simulation & evaluation
- [x] Scenario library per agent (all 14 categories across the catalog; Finance covers all 14), expected outcomes,
      deterministic assertions; custom scenarios from expectations; stored per workspace, versioned
- [x] Scenario execution with traces (sandbox tools behind the governance dispatcher, background job on the worker);
      scoring per SPEC dimension with per-agent thresholds; mandatory security checks — dev planner = labelled scripted
      attempts; model planner tested with a fake client only (**no live model call**)
- [x] Failure analysis + suggested config changes (narrowing ones applicable → new version); refine & re-run; rollback
- [x] Readiness gate → Ready for Deployment; CEO activation approval; observation first stage, widening needs a new
      passing run; pause/resume with regression check after material changes

## Phase 5 — Controlled execution
- [x] Tool registry (input/output schemas, scope → risk, validation rules, approval, timeout, retry, idempotency,
      audit; code-defined and versioned, ADR-025); no SQL/shell/HTTP tool; catalog tools without an integration are
      registered as *not connected* and refused
- [x] Shared governance dispatcher (`governance/dispatch.py`) used by the simulation sandbox and real execution
- [x] Business records module (invoices + lines, payments, expenses, drafts; validated Decimal calculations,
      insert-only lines/payments) with API + page; real read-only tools (`invoices.read`, `expenses.read`,
      `reports.read`, `kpi.read`, `knowledge.search`), drafts (`reminder.draft`, `briefing.draft`), `escalate`, and one
      approval-bound external tool (`reminder.send` → mail adapter; **dev outbox only — no real delivery verified**)
- [x] Orchestrator (explicit state machine; planner → dispatcher → tool → validator, one step at a time; Executive
      delegates one level; no agent-to-agent chat) — dev planner = labelled playbooks; model planner tested with a
      fake client only (**no live model call**)
- [x] Scheduling (weekly/monthly in the company time zone with hours + holidays; events incl. invoice.overdue;
      business-hours deferral), background execution on the worker, run locking, daily limits, idempotency keys
- [x] Approval enforcement bound to exact resolved parameters + config hash + policy version; re-approval on change
- [x] Execution evidence (write-once ledger) + audit trail; unknown outcomes marked unverified and never repeated

## Phase 6 — Reporting & notifications
- [x] Activity records (agent "Activity history", Control Center recent activity); daily reports projected from
      execution records — all 15 SPEC sections, evidence links indexed in `report_evidence`, final after the local day
- [x] Task completion verification: attempted vs completed vs unverified per action; unknown outcomes listed until
      reconciled (insert-only reconciliations from the mail outbox) — **SMTP reconciliation tested with a simulated
      outbox status only; no real SMTP delivery made**
- [x] CEO Control Center metrics + filters (agent, department, status, date range, priority), agent performance tab
- [x] In-app notifications, email adapter (dev outbox — **no real delivery verified**), SMS adapter interface (dev
      provider only — **no real SMS provider exists**); recipients by permission, preferences, delivery limits, daily
      digests in the company time zone, delivery records, bounded retries with backoff
- [x] Usage & cost tracking (by agent, purpose, day; dev calls labelled), agent budgets enforced at claim time,
      company budget compared in USD

## Phase 7 — Hardening & production readiness
- [x] Full E2E journey test — SPEC §9's 14 steps in one Playwright spec through the UI on the real stack
      (`e2e/journey.spec.ts`, + pause/edit/re-approve/re-test/resume, data controls); tenant isolation: every
      workspace route denies anonymous/non-members live (`test_security_surface.py`) on top of the per-phase suites;
      RAG security suite (`test_knowledge_security.py`, evals) unchanged and green
- [x] Security review (`docs/SECURITY.md`): route-walking authz test, `ai_work` rate limits per user + workspace,
      secrets out of `repr`, production guards; data retention (per-workspace windows + housekeeping purges), owner-only
      export, scheduled workspace deletion on the owner path (`test_privacy.py`)
- [x] Observability: JSON logs with request/job/run ids, error-reporting sink (API + jobs; Sentry adapter **not
      live-verified**), Prometheus `/api/metrics` (`test_observability.py`); backup & restore scripts with a recorded
      restore drill (`docs/OPERATIONS.md`)
- [~] Deployment docs (`docs/DEPLOYMENT.md`), Dockerfiles, prod compose example, CI workflow; performance (constant
      query counts on every list/dashboard/report endpoint, new indexes — `test_performance.py`). Backend image built
      and smoke-tested; **web image build not verified** (stopped after 50 min in `npm ci`) and **the CI workflow has
      not run** (no commits/remote) — see STATUS
- [x] Continuous evaluation controls (SPEC §4): pause/resume/edit/re-test/rollback/retire existed (Phases 3–4);
      Control Center now lists agents affected by a material change until re-tested (`test_continuous_eval.py`)

## Phase 8 — Design: platform identity + tenant branding
Direction chosen with the user: **The Annual Report** (`.impeccable/surfaces/frontend-src-app-app.md`, ADR-035).
Product context: `PRODUCT.md`; visual system recorded in `DESIGN.md` at the end.
- [x] Platform identity: logo mark, palette and type tokens (light + dark), shell (green rail with brass rule,
      workspace block, daily-review-first navigation), shared components (buttons, glyph+word badges, ruled tables,
      report sections, forms) and public pages (landing as a report cover + contents page, auth)
- [x] Signature move: report-scale figures with superscript note keys that open Notes linking to their records
      (Control Center, daily reports)
- [x] Raises: budgets as capacity bars (usage, Control Center); states as glyph + word; readiness shows the next
      step and what it unlocks; the approval inbox focuses one held action with the queue beside it
- [x] Tenant branding backend: logo upload (magic-byte sniffing, 1 MB / 4096 px limits, re-encoded PNG, SVG refused),
      palette extraction, brand-as-fill when it carries text at 4.5:1, hue-preserving text accent fitted to every
      surface of both themes, rail marker ≥ 3:1, brass-like accents switch note keys to ink, type mood from industry,
      owner overrides; API with permissions, RLS, audit, export + deletion coverage (`test_branding.py`)
- [x] Tenant theming frontend: runtime `--brand-*`/`--mood-*` tokens, workspace logo in the rail, Settings → Branding
      with palette, contrast checks, adjustments and live preview
- [x] Verified: pytest 568 passed; lint/typecheck/build clean; Playwright 9/9 incl. `phase8.spec.ts` (yellow logo
      workspace) with axe AA on every page; desktop + mobile screenshots; impeccable detector clean; finish review
      (two fix rounds — see STATUS)
