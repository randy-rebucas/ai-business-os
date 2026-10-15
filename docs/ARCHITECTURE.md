# AI Business OS — Architecture

Source of truth for requirements: `docs/SPEC.md`. Settled choices and their reasons: `docs/DECISIONS.md`.
Phase checklist: `docs/PHASES.md`. Current state and session log: `docs/STATUS.md`.

## 1. Shape of the system

A **modular monolith** (ADR-001): one FastAPI service, one Next.js app, one Postgres database, plus Redis and a
background worker. Each module owns its tables, schemas, service layer and router; modules call each other only
through service functions, never through another module's tables or routers.

```
Browser ──► Next.js (3470) ──/api rewrite──► FastAPI (8470) ──► Postgres 16 + pgvector (55470)
                                                 │                    ▲
                                                 ├──► Redis (56470) ──┤  Celery broker / locks
                                                 │                    │
                                                 └──► Worker (Celery) ┘  ingestion, embeddings, schedules,
                                                                         agent runs, reports, notifications
                                         Object storage (local dir in dev, S3-compatible in prod)
                                         LLM / embedding providers (behind the gateway, server-side only)
```

The spec's four responsibilities map to four layers that never collapse into each other:

| Responsibility | Where | Rule |
|---|---|---|
| Business systems (authoritative records) | `company`, `business` (Phase 5 records), `identity` | Deterministic services + DB constraints. AI never owns balances, totals, permissions, statuses. |
| RAG & knowledge | `knowledge` | Retrieval is tenant- and permission-filtered **in SQL**, before any text reaches a model. |
| AI agents | `agents`, `llm` | Interpret, analyse, plan, call **registered tools only**. Output is a proposal until validated. |
| Governance & orchestration | `governance` (approvals, policies), `orchestration`, `audit` | Backend-enforced permissions, approvals bound to exact action parameters, append-only evidence. |

## 2. Backend modules (`backend/abos/`)

| Module | Phase | Owns |
|---|---|---|
| `core` | 1 | config, DB engine/session, tenancy (RLS context), errors, logging, rate limits, security helpers |
| `identity` | 1 | users, organizations, memberships, roles → permissions, sessions, auth tokens, outbox mail |
| `audit` | 1 | append-only `audit_events` + query API |
| `company` | 1 | company profile, locations, departments, job roles, products/services, objectives/KPIs, processes, software, challenges, onboarding completeness |
| `storage` | 2 | object storage adapter (local / S3), signed downloads |
| `llm` | 2 | provider-independent gateway: chat, embeddings, (rerank); usage ledger; dev adapter labelled |
| `knowledge` | 2 | documents, versions, chunks (+ vectors, tsvector), ingestion pipeline, hybrid retrieval, citations, RAG evals, business interview |
| `jobs` | 2 | Celery app, durable job records, retry/timeout policy |
| `agents` | 3 | agent definitions (catalog), instances, versioned configurations, task definitions + dependencies, permission scopes, schedules, lifecycle, execution guard |
| `governance` | 3 | business rules (fact → proposed → confirmed), policy versions, approvals |
| `simulation` | 4 | scenarios, suites, runs, deterministic assertions, readiness gate |
| `tools` | 5 ✓ | code-defined tool registry (schemas, risk, approval, timeouts, retries, idempotency), handlers, write-once execution ledger (ADR-025) |
| `orchestration` | 5 ✓ | workflow runs (= task runs), planner → dispatcher → tool → validator, events, scheduler, delegation (ADR-027) |
| `business` | 5 ✓ | authoritative records the first tools act on: invoices, lines, payments, expenses, drafts (ADR-028) |
| `reporting` | 6 ✓ | daily reports projected from execution records, Control Center metrics (ADR-029) |
| `notifications` | 6 ✓ | in-app + email + SMS adapter interface, preferences, limits, digests, deliveries with retries (ADR-030) |
| `usage` | 6 ✓ | usage & cost summaries from `model_usage`, enforced agent budgets (ADR-031) |

Business logic lives in `service.py` files. Routers only parse, authorize (dependency) and call services.

## 3. Tenancy and authorization (security-critical)

1. **Session cookie** (httpOnly, SameSite=Lax, opaque token, only its SHA-256 stored) → `current_auth`.
2. **Active organization** comes from the `X-Org-Id` header and is **verified against `organization_memberships`
   server-side** (`require_org_member`). The org id in a body or path is never trusted.
3. **Permissions, not roles**, are checked in routers (`require_org_permission("company.write")`); the role→permission
   map is `identity/permissions.py` (ADR-004).
4. **Postgres row-level security** is the second layer (ADR-003): every tenant table has
   `organization_id` + a `tenant_isolation` policy; the API connects as the non-owner role `abos_app`;
   `set_tenant()` sets `app.org_id` per transaction. A test fails if a tenant table lacks a policy.
5. **CSRF**: unsafe `/api/*` methods require `X-Requested-With: abos` (browsers can't send it cross-site).
6. **Audit**: `audit_events` is append-only (DB trigger + no UPDATE/DELETE grant to the app role).
7. Later phases add: document-level access classifications filtered in retrieval SQL (Phase 2), agent permission
   scopes + approvals bound to a hash of the exact action parameters and policy version (Phases 3/5).

### Org roles (workspace administration) vs business title

`organization_memberships.role` ∈ `owner | admin | manager | member | viewer` controls the workspace.
`organization_memberships.job_title` (e.g. "CEO") is a business title with **no** authorization meaning (spec §3 step 1).

## 4. Data model

Relational tables per entity, JSONB only for flexible configuration/metadata (ADR-005). Every tenant row carries
`organization_id` (FK → organizations, `ON DELETE CASCADE`), `created_at`, `updated_at`.

| Spec entity | Table(s) | Phase |
|---|---|---|
| Organizations / Users / Memberships | `organizations`, `users`, `organization_memberships` | 1 |
| Roles and permissions | code-defined map (`identity/permissions.py`) + `membership.role` | 1 |
| Sessions, tokens, mail | `user_sessions`, `auth_tokens`, `authentication_events`, `email_outbox` | 1 |
| Company profiles | `company_profiles` (1:1 org) | 1 |
| Departments | `departments`, `job_roles` | 1 |
| (profile detail) | `company_locations`, `products_services`, `business_objectives`, `business_processes`, `software_systems`, `operational_challenges` | 1 |
| Audit events | `audit_events` | 1 |
| Rate limits | `rate_limit_buckets` | 1 |
| Documents / versions / chunks | `documents`, `document_versions`, `document_chunks` (vector(1024) HNSW + generated tsvector GIN) | 2 ✓ |
| Knowledge sources | `documents.source_type` = upload \| url (no separate table needed yet) | 2 ✓ |
| Answers given (evidence) | `knowledge_queries` (insert-only for the app role) | 2 ✓ |
| Interview | `interview_questions` | 2 ✓ |
| RAG evaluation | `rag_eval_cases`, `rag_eval_runs`, `rag_eval_results` | 2 ✓ |
| Jobs | `job_runs` | 2 ✓ |
| Usage records | `model_usage` (insert-only for the app role) | 2 ✓ |
| Policies / policy versions | `business_rules` (status per item); policy version derived from the confirmed set (ADR-017) | 3 ✓ |
| Agent definitions / instances / configurations / permissions / assignments | `agent_definitions` (platform, read-only to the app), `agent_instances`, `agent_configurations` (versioned JSONB incl. permission scopes + knowledge access, ADR-018) | 3 ✓ |
| Tasks / dependencies | `task_definitions`, `task_dependencies` (per configuration version) | 3 ✓ |
| Approvals | `approvals` (insert-only decision ledger, hash + policy version bound) | 3 ✓ |
| Simulation scenarios / evaluation results | `simulation_scenarios`, `simulation_runs`, `simulation_results`; `agent_instances.deployment_stage` | 4 ✓ |
| Tool definitions / executions | registry in code (ADR-025); `tool_executions` (write-once ledger, unique idempotency key) | 5 ✓ |
| Workflow runs / action approvals | `workflow_runs` (task runs; unique idempotency key), `action_requests` | 5 ✓ |
| Business records | `invoices`, `invoice_lines`, `payments` (insert-only), `expenses`, `drafts` | 5 ✓ |
| Integration credential references | `integrations` (secret refs only, encrypted) | later (no external integration yet) |
| Notifications | `notifications`, `notification_preferences`, `notification_deliveries` | 6 ✓ |
| Daily reports | `daily_reports`, `report_evidence`; `execution_reconciliations` (insert-only) | 6 ✓ |

## 5. API contracts (versioned under `/api/v1`)

Errors always use `{"error": {"code", "message", "details"}}`. Tenant endpoints require `X-Org-Id`.

**Phase 1**
- `POST /api/v1/auth/register` {email, password, full_name, organization_name, job_title?} → Me (sets cookie; user becomes **owner**)
- `POST /api/v1/auth/login` · `POST /api/v1/auth/logout` · `GET /api/v1/auth/me`
- `POST /api/v1/auth/verify-email` · `POST /api/v1/auth/verify-email/resend`
- `POST /api/v1/auth/password-reset/request` · `POST /api/v1/auth/password-reset/confirm` · `POST /api/v1/auth/password`
- `POST /api/v1/orgs` (create another workspace; caller becomes owner)
- `GET|PATCH /api/v1/org` · `GET|POST /api/v1/org/members` · `PATCH|DELETE /api/v1/org/members/{user_id}`
- `GET|PATCH /api/v1/company/profile` (partial update; null clears) · `GET /api/v1/company/completeness` ·
  `POST /api/v1/company/onboarding/complete` · `GET /api/v1/company/timezones`
- `GET /api/v1/auth/sessions` · `DELETE /api/v1/auth/sessions/{id}`
- `GET|POST /api/v1/company/{collection}` · `PATCH|DELETE /api/v1/company/{collection}/{id}` for
  `locations | departments | job-roles | offerings | objectives | processes | software | challenges`
- `GET /api/v1/audit`
- `GET /api/health`, `GET /api/health/ready`

**Phase 2** (built) — `GET|POST /api/v1/documents` (multipart upload) · `POST /documents/url` ·
`GET|PATCH /documents/{id}` · `GET /documents/{id}/chunks` · `POST /documents/{id}/{versions|retry|reprocess|review|archive|restore}` ·
`GET /documents/{id}/download?version_id=` · `GET /api/v1/knowledge/status` · `POST /knowledge/search` ·
`POST /knowledge/ask` · `GET /knowledge/queries` · `GET|POST /knowledge/evals/cases`, `DELETE /knowledge/evals/cases/{id}` ·
`GET|POST /knowledge/evals/runs`, `GET /knowledge/evals/runs/{id}` · `GET /api/v1/interview` ·
`POST /interview/generate` · `POST /interview/{id}/{answer|dismiss}`. Pipeline details: `docs/RAG.md`.

**Phase 3** (built) — `GET /agents/policy` · `GET /agents/catalog[/{key}]` · `GET /agents/recommendation` ·
`GET|POST /agents` · `GET /agents/{id}` (detail incl. tasks, approvals, execution guard) ·
`POST /agents/{id}/config/{generate|submit}` · `PUT /agents/{id}/config/draft` · `GET /agents/{id}/config/versions[/{n}]` ·
`GET /agents/{id}/schedule` · `POST /agents/{id}/retire` · `GET|POST /rules` · `POST /rules/extract` ·
`POST /rules/{id}/review` · `GET /approvals` · `GET /approvals/pending` · `GET /approvals/configurations/{id}` ·
`POST /approvals/configurations/{id}/decide`. Details: `docs/AGENTS.md`.

**Phase 4** (built) — `/simulations/scenarios`, `/simulations/runs[/{id}]`,
`/simulations/results/{id}/suggestions/{i}/apply`, `/agents/{id}/simulations`, `/agents/{id}/readiness`,
`/agents/{id}/{activate|widen|pause|resume}`, `/agents/{id}/config/rollback`. Details: `docs/SIMULATION.md`.

**Phase 5** (built) — `GET /tools` · `GET /tools/executions` · `GET|POST /workflows` · `GET /workflows/tasks` ·
`GET /workflows/{id}` · `POST /workflows/{id}/cancel` · `GET /approvals/actions[/{id}]` · `POST /approvals/actions/{id}/decide` ·
`GET|POST /business/invoices` · `GET /business/invoices/{id}` · `POST /business/invoices/{id}/{payments|void}` ·
`GET /business/receivables` · `GET|POST /business/expenses` · `GET /business/drafts` · `POST /business/drafts/{id}/discard`. Details: `docs/EXECUTION.md`.

**Phase 6** (built) — `GET /reports` · `POST /reports/generate` · `GET /reports/{id}` · `GET /dashboard` (filters: agent_id, department, status, date_from, date_to, priority) · `GET /notifications` · `GET /notifications/unread-count` · `POST /notifications/{id}/read` · `POST /notifications/read-all` · `GET|PUT /notifications/preferences` · `GET /notifications/deliveries` · `GET /usage`. Details: `docs/REPORTING.md`.

## 6. Frontend (`frontend/`)

Next.js 16 (App Router) + React 19 + TypeScript + Tailwind v4 + shadcn-style local components (`src/components/ui`,
ADR-007). All API calls go through the same-origin `/api` rewrite so the session cookie is first-party. Tenant reads
use SWR keys `[path, orgId]` so switching workspace never shows another org's cached data. Nonce CSP in `src/proxy.ts`.

Route groups: `(public)` landing · `(auth)` login/register/forgot/reset/verify · `/app/*` authenticated shell
(onboarding wizard, dashboard, company, settings, audit; later knowledge, agents, simulations, approvals, reports…).

## 7. Background execution (Phase 2+)

Celery with a Redis broker (ADR-008); **durable state is in Postgres** (document status, `job_runs`, later
`task_runs`/`workflow_runs`), so a lost Redis message is recoverable by a sweeper that re-enqueues stale jobs.
Workers run `--pool=solo` on Windows. Tests run tasks eagerly. No LLM request is held open across a workflow; each
step is its own job with a timeout and bounded retries.

## 8. AI layer (Phase 2+)

`llm.gateway` exposes `chat()`, `embed()`, `rerank()` with per-purpose model selection (reasoning, document analysis,
embedding, evaluation). Providers: `dev` (deterministic, always labelled "Development adapter", refuses to start in
production), `anthropic` (Claude via the official SDK), embeddings `hash` (dev) / `voyage` / `openai-compatible`.
Keys are server-side only. Every call writes a `model_usage` row (tokens, cost estimate, purpose, agent, org).
