# AI workforce: catalog, configuration & approval (Phase 3)

Implements SPEC §3 steps 2, 4 and 5. Code: `backend/abos/agents/`, `backend/abos/governance/`.
Pages: `/app/agents` (directory), `/app/agents/catalog`, `/app/agents/team`, `/app/agents/[id]` (profile tabs),
`/app/agents/[id]/configure`, `/app/rules`, `/app/approvals`, `/app/approvals/[configId]` (approval summary).

## Lifecycle (server-side state machine — `agents/lifecycle.py`)

```
available (catalog, no instance)
  └─hire─► selected ─generate/edit─► configuring ─submit─► awaiting_approval ─CEO approves─► testing
                                        ▲   ▲                    │ CEO requests changes            │ (Phase 4 readiness)
                                        │   └────────────────────┘                                 ▼
                                        └──────── any edit of an approved config ──── ready_for_deployment ─► active ⇄ paused
  any live state ─► failed (→ configuring) · any state ─► retired (terminal; the agent can be hired again)
```
`testing`, `ready_for_deployment`, `active` and `paused` require `approved_config_id == current_config_id` — checked
inside `transition()`, so no endpoint can skip the CEO. Phase 3 exposes hire, generate, edit, submit, decide and retire;
activation arrives with Phase 4's readiness gate.

**Execution guard** — `agents.service.execution_allowed(db, instance)` is the one check Phase 5 tools must call. True
only when the agent is `active`, its current configuration is the approved one, a hash re-computed from the database
rows equals the hash recorded in the `approvals` row, and that decision was `approved`. A configuration changed behind
the API therefore stops execution (tested).

## Catalog (`agent_definitions`)

Agents A–H live in `agents/catalog_v1.py` and are seeded by migration 0003. The module is **frozen**: publish a new
version as `catalog_v2.py` + a migration that inserts it and clears `is_current` on the old row. Instances keep the
version they were hired with. The app role can read the table but not change it. Each definition carries every SPEC
profile field (identity, department, expertise, responsibilities, prohibited activities, knowledge, tools,
permission ceilings, escalation conditions, KPIs, reporting, model, budget, default operating mode), task templates and
recommendation signals.

## Recommended team (`agents/recommend.py`)

Deterministic and explained — no model. Signals per definition (department names, job roles, software categories,
challenge and objective keywords, approved document types, product offerings, process count, headcount) add weighted
points with a human-readable reason; score ≥ 2 recommends. Executive is added once two others are. With a USD budget the
weakest are dropped until the estimate fits; a non-USD budget is reported as *not comparable* (no exchange rates are
invented). Profile gaps that would improve the result are listed. The CEO can accept the team or build a custom one.

## Permission model (`agents/policy.py`)

| Scope | Risk | Platform ceiling | Default |
|---|---|---|---|
| data.read | low | auto | auto |
| records.draft | low | auto | auto |
| records.modify | medium | auto | approval required |
| comms.external | high | auto | approval required |
| transactions.create | high | approval required | approval required |
| transactions.approve | critical | **denied** (always a human) | denied |
| finance.execute | critical | approval required | denied |
| documents.sensitive | high | auto | denied |

Each definition has its own ceilings (e.g. Finance: `finance.execute` denied — it never issues payments). A config mode
above either ceiling is a validation **error**. Templates start at min(default, ceilings); observe-only agents start
with every write scope denied. Tasks that use an approval-required scope must be marked as needing approval.

## Configuration (`agent_configurations` + `task_definitions` + `task_dependencies`)

The configuration is a Pydantic-validated JSON document (`schemas.AgentConfig`): job description (title, department,
mission, scope, included/excluded tasks, required knowledge, data sources, authorised tools, priority rules,
dependencies, escalation policies, approval requirements, success metrics), reporting, operating mode with separate
monitoring and execution windows, permissions, knowledge access, model, limits and automation level. Tasks are rows
(trigger, schedule/event, inputs, steps, output, completion criteria, dependencies, priority, SLA, policy refs,
permissions, approval, failure/retry policy) so later phases can schedule them.

- **Versioning**: a draft is edited in place; once submitted, approved or rejected it is frozen and the next save
  creates version n+1 (a pending submission becomes `withdrawn`). The hash (`sha256` of canonical config + tasks)
  identifies exactly what was reviewed.
- **Validation** (`agents/validation.py`): structural errors are 422; contextual problems are returned as issues —
  errors block submit/approve (ceilings, unknown/denied tools, sensitive documents without the scope, time zone or hours
  missing, task outside business hours, unsupported event, unknown/self/cyclic dependencies, unconfirmed policy refs),
  warnings don't (budget above the company budget, mode/trigger mismatch, no tasks).
- **Schedules** (`agents/schedule.py`): company time zone; weekly runs skip closed days and holidays in a business-hours
  window; monthly runs falling on a closed day move to the next opening; events noticed after hours wait for the next
  opening unless critical. `/agents/{id}/schedule` previews the next runs.

## Generation (`agents/design.py`)

1. Template from the catalog, fitted to the company (reporting cadence; scheduled tasks moved inside opening hours with
   a recorded adjustment).
2. Confirmed business rules for this agent are attached (approval/escalation lines, task policy refs). Rules not yet
   confirmed are listed as open questions and **not applied**. Approved knowledge is retrieved per the definition's
   queries and recorded as evidence.
3. With a real model, only text may change (mission, scope, responsibilities, task descriptions) plus up to three extra
   on-demand read-only tasks. Permissions, triggers, schedules, budgets and approval flags never come from the model.
   Citations are verified verbatim; text with figures found in no source is rejected with a warning. The dev adapter
   performs no refinement and is labelled.

## Business rules (`governance/rules.py`, ADR-017)

Statuses: **fact** (stated in a source) · **proposed** (an interpretation that would change behaviour) · **unresolved**
(a question the sources leave open) · **conflicting** (sources disagree) · **confirmed** · **rejected**. Sources:
approved documents (retrieved per SPEC topic with the same filters as Ask), interview answers, the company profile, and
manual entries. A document item must quote its source verbatim and every figure in its statement must appear in the
quote, otherwise it is dropped and reported. Thresholds are parsed from the quote by regex, never from model output.
Conflicts (same subject, different amounts, different sources) are detected deterministically. A rule whose cited
document is no longer indexed is flagged stale on every read and is not used. Unresolved questions need an answer to be
confirmed. Re-extraction never duplicates or resets a reviewed rule. Rules carry the highest access level of their
sources and are filtered like documents.

## Approvals (`governance/approvals.py`)

`POST /approvals/configurations/{id}/decide {decision, note, config_hash}` — owner only (`approval.decide`). Accepted
only for the agent's current submitted configuration when the reviewed hash equals the stored hash and a hash
re-computed from the rows. Validation errors are re-checked at decision time. Requesting changes needs a note. The
`approvals` row (insert-only for the app role) records user, role, decision, time, version, hash, policy version
(`platform-2026.10/rules-<n>-<digest of confirmed rules>`) and the exact scope authorised.

## API (`/api/v1`)

`GET agents/policy` · `GET agents/catalog[/{key}]` · `GET agents/recommendation` · `GET|POST agents` ·
`GET agents/{id}` · `POST agents/{id}/config/generate` · `PUT agents/{id}/config/draft` ·
`POST agents/{id}/config/submit` · `GET agents/{id}/config/versions[/{n}]` · `GET agents/{id}/schedule` ·
`POST agents/{id}/retire` · `GET rules` · `POST rules` · `POST rules/extract` · `POST rules/{id}/review` ·
`GET approvals` · `GET approvals/pending` · `GET approvals/configurations/{id}` ·
`POST approvals/configurations/{id}/decide`.
Permissions: read = `agent.read`; generate/edit/submit = `agent.configure` (manager+); hire/retire = `agent.hire`
(admin+); decide = `approval.decide` (owner); rules review = `rule.review` (manager+), rules list = `knowledge.read`.
