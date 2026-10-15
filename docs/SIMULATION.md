# Simulation, readiness & deployment (Phase 4)

Implements SPEC §3 step 6 and the deployment controls of SPEC §4. Code: `backend/abos/simulation/`.
Pages: `/app/agents/[id]/readiness` (checklist, run, activate, widen, pause/resume), `/app/simulations/runs/[id]`
(scores, per-scenario assertions, action trace, failure analysis + apply), `/app/simulations` (all runs, scenario
library, custom scenarios), agent profile tabs "Test results" and "Configuration versions" (restore).

## How a scenario runs (`runtime.py`, `sandbox.py`)

```
scenario (request, question, fixtures, faults) + agent's current configuration + confirmed threshold rules
  │
  ├─ knowledge.search through the dispatcher (no read permission → no sources)
  │     fixture documents (tenant / status / type / access-level filtered) + the org's approved documents
  │     instruction-like text redacted before any planner sees it
  ├─ plan: real model → proposed tool calls + answer   ·   dev → the scenario's scripted attempts (labelled)
  ├─ every call → dispatcher: known tool? valid input? authorised? scope denied? deployment stage? money above a
  │     confirmed limit / no limit? approval-required scope or task? duplicate for this trigger? faults + retries
  │     → executed | blocked | held_for_approval | rejected | rejected_input | failed | duplicate_suppressed
  └─ answer verified like Ask (quotes must be in the source, figures supported) → outcome completed/escalated/incomplete
```
Nothing leaves the sandbox: tools act on fixtures. The dispatcher's decision path is the governance code Phase 5 will
put in front of real tools. Records of another organisation are invisible ("not found"). Invoice figures are checked
by validated Decimal arithmetic (`invoice_checks`), never by the model.

**Dev mode is honest about what it proves.** With the dev adapter the plan is the scenario's scripted attempts (what a
naive or compromised agent would try), so a dev run verifies the *platform and the configuration*: whether each
attempted action is refused, held or allowed, whether knowledge access works, retries, idempotency, isolation and
injection redaction. Behavioural dimensions that depend on a planner (choosing to escalate, choosing tools) are only
meaningful with a real model; the run page labels the planner.

## Library (`library.py`)

Every catalog agent gets scenarios built from its own tools: normal operations, missing information, conflicting
policies, outdated documents, unauthorised request (bank details change), insufficient permissions (pay + self-approve),
failed integration, transient timeout, duplicate trigger (agents with a drafting tool), malicious document, another
organisation's data, escalation, and approval-required (agents with an external/modify/transaction tool). Domain
scenarios: Finance — outstanding invoice review, invoice discrepancy; Support — refund above the automatic limit (the
SPEC example), complaint escalation. Finance covers all 14 categories; the union covers all 14 for every agent
type. Library scenarios are copied per workspace (versioned, `LIBRARY_VERSION`); custom scenarios are created from
simple expectations (answer must mention / must never say / must escalate / action that must never run) that the
platform turns into assertions.

## Grading (`evaluation.py`, ADR-022)

Deterministic assertions only (no LLM judge), each mapped to one of the ten SPEC dimensions. `mandatory` assertions are
security/authorisation checks — one failure fails the run regardless of scores. Thresholds per agent type
(`AGENT_THRESHOLDS`; Finance: overall 95 %, correctness and grounding 100 %). Failure analysis explains each failed
check and proposes changes; only *narrowing* changes can be applied with a click (deny / require approval, mark task
for approval, add an escalation line, add retries) — they create a new draft version that needs approval and testing
again. Widening (e.g. more document types) is always a manual CEO edit (SPEC §4).

## Readiness gate & deployment (`service.py`, ADR-023)

Ready requires: current configuration approved; a completed run of exactly that configuration (stored hash = hash
recomputed now); the run passed; the confirmed-rule policy version unchanged since the run; every active required
scenario included at its current version. A passing run moves `testing → ready_for_deployment`.

| Action | Who | Requires | Records |
|---|---|---|---|
| Run tests | `simulation.run` (manager+) | a configuration | run + results (background job) |
| Activate | `agent.activate` (owner) | ready + reviewed hash | approval `activation`, stage `observation` |
| Widen | owner | active, observation, ready, a passing run *after* activation | approval `deployment_stage`, stage `full` |
| Pause | owner | active | audit |
| Resume | owner | ready (regression after any material change) | audit |
| Restore version | `agent.configure` | a previously approved version | new draft → approval + testing again |
| Apply suggestion | `agent.configure` | run of the current configuration; narrowing only | new draft version |

`execution_allowed(db, instance, scope)` now also requires activation and, in observation, only allows `data.read`
and `records.draft`.

## API (`/api/v1`)

`GET simulations/scenarios?agent_key=` · `POST simulations/scenarios` · `DELETE simulations/scenarios/{id}` ·
`GET simulations/runs` · `GET simulations/runs/{id}` · `POST simulations/results/{id}/suggestions/{i}/apply` ·
`POST|GET agents/{id}/simulations` · `GET agents/{id}/readiness` · `POST agents/{id}/{activate|widen|resume}`
`{config_hash, note?}` · `POST agents/{id}/pause {reason?}` · `POST agents/{id}/config/rollback {version}`.
