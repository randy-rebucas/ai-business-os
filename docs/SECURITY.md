# Security & authorization

Audience: reviewers and maintainers. Architecture in `ARCHITECTURE.md` §3; decisions referenced as ADR-nnn.

## Controls (SPEC §6) and where they are enforced

| Control | Implementation | Proven by |
|---|---|---|
| Tenant isolation | `require_org_member` resolves `X-Org-Id` against memberships server-side (never trusted), then binds the session to the tenant; Postgres RLS on every tenant table as the second layer, API runs as non-owner `abos_app` (ADR-003) | `test_rls.py` (every tenant table has a policy), `test_tenancy.py`, per-phase tenancy tests, `test_security_surface.py` (every route, non-member → 403) |
| Authorization | named permissions (`identity/permissions.py`), never roles or titles (ADR-004); every workspace route declares one (ADR-034) | `test_security_surface.py` (static walk + live viewer checks on every route above viewer level, 80+) |
| Sessions | opaque token, only its hash stored, httpOnly + SameSite=Lax, `__Host-`/Secure in production, revocable, password change revokes others | `test_auth.py` |
| CSRF | `X-Requested-With: abos` on unsafe methods + SameSite (ADR-009) | `test_auth.py` |
| Rate limiting | Postgres fixed windows shared by instances: login/register/reset per IP & email, sensitive actions per user, Ask per user, `ai_work` (generation, simulations, runs, reports, ingestion, extraction, evals) per user **and** per workspace, exports per user; consistent 429 + `Retry-After` | `test_security_surface.py`, `test_auth.py` |
| Input validation | Pydantic schemas (extra fields forbidden where it matters), body size caps, upload byte sniffing, SSRF-guarded URL import | `test_knowledge_ingest.py`, `test_knowledge_security.py` |
| Secrets | env only; `SecretStr` / `repr=False` for DB URL, SMTP, API keys; production refuses dev values | `test_security_surface.py::test_production_settings_refuse_unsafe_values` |
| Headers | API: CSP `default-src 'none'`, nosniff, DENY framing, no-store, HSTS when secure; web: nonce CSP (`src/proxy.ts`) | `test_security_surface.py`, `test_auth.py` |
| Audit | append-only `audit_events` (trigger + revoked grants) | `test_audit.py` |
| RAG security | review gate, access levels and filters in retrieval SQL, injection redaction, deterministic citation/figure checks (ADR-013/015) | `test_knowledge_security.py`, `test_knowledge_evals.py`, Phase 2 E2E |
| Agent governance | code-defined scopes/ceilings, hash-bound approvals, one dispatcher for sandbox and execution, parameter-bound action approvals, write-once evidence (ADR-019/025/026) | `test_agents_*`, `test_simulation.py`, `test_execution.py` |
| Financial safety | Decimal calculations, insert-only payments/lines, idempotency keys, unknown outcomes never success (ADR-028) | `test_execution.py` |
| Data retention & deletion | retention windows, owner-only export, scheduled deletion on the owner path (ADR-033) | `test_privacy.py` |
| Error handling | one sink, generic 500 with request id, no internals leaked (ADR-032) | `test_observability.py` |

## Phase 7 review — findings and fixes (2026-10-15)
1. **The database URL (with password) appeared in `repr(Settings)`** → excluded from repr; test asserts no secret
   appears.
2. **No rate limit on endpoints that start model calls or worker jobs** (generation, simulations, runs, reports,
   ingestion, extraction, evals) → `ai_work` limit per user and per workspace; a route-walking test fails if such a
   route loses it.
3. **No data deletion or export** (SPEC §6) → retention settings + purges, owner-only export, scheduled workspace
   deletion with confirmation, grace period and cancellation.
4. **Usage endpoint ran one query per agent and aggregated every usage row in Python** → SQL aggregation; all list,
   dashboard and report endpoints are now checked for constant query counts.
5. **Material changes didn't identify affected agents** (SPEC §4) → Control Center "Needs re-testing".
6. Verified, no change needed: every one of the 160+ routes requires a session except 8 deliberate public ones; every
   workspace route checks a named permission; anonymous/non-member/viewer denials hold live for all of them.

## Residual risks (accepted for now, tracked in STATUS.md)
- In development the app logs in as the table owner and `SET ROLE`s down; production must use a login that is only a
  member of `abos_app` (DEPLOYMENT.md §2).
- No MFA/SSO; no malware scanning of uploads (`scan_status = not_scanned`); DNS-rebinding window on https URL import
  (route egress through a proxy that blocks private ranges).
- Real providers (Claude, embeddings, SMTP, S3, Sentry) are implemented but not live-verified; SMS has no real provider.
- Audit events of a deleted workspace are kept (detached) indefinitely; purge them per your legal retention policy.
