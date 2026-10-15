# Controlled execution (Phase 5)

Implements SPEC §3 step 7 (orchestration, tool registry, tool execution), the human-approval and financial-safety
parts of SPEC §6, and the first real business tools. Code: `backend/abos/{governance/dispatch.py, tools, orchestration,
business, governance/actions.py}`. Pages: `/app/tasks` (run approved tasks, ask an agent, all runs),
`/app/tasks/[id]` (result, checks, delegated runs, evidence ledger, approvals), `/app/approvals` (agent actions
waiting + decisions), `/app/records` (invoices, payments, expenses, drafts), agent profile tab "Activity history".

## One step of a run (`orchestration/service.py`)

```
planner.next_action(observations so far)            dev: deterministic playbook (labelled) · real model: gateway
  │  → {call tool, input} | {finish, summary, findings, missing_evidence, criteria}
  ├─ tool in the agent's registry?                    no → unknown_tool
  ├─ input valid against the tool's Pydantic schema?  no → rejected_input
  ├─ agents.execution_allowed(inst)                   no → blocked, run stops (paused / config changed / not active)
  ├─ governance.dispatch.decide(...)                  the SAME function the simulation sandbox uses (ADR-025)
  │     blocked → blocked · tool approval "always" → held · not connected → unavailable
  ├─ held → exact parameters resolved (e.g. recipient, subject, full text) → params_hash(tool, parameters,
  │     instance, config hash, policy version) → approved request with that hash? use it once
  │     · rejected? → rejected · otherwise raise/keep an action request; run → awaiting_approval
  ├─ side effect → idempotency key sha256(instance|tool|input|run idempotency key), unique per workspace:
  │     already succeeded → duplicate (reuses the result) · already attempted, outcome unknown → unverified, not repeated
  ├─ agents.execution_allowed(inst, scope, approved_action=…)  (observation stage lets an approved action through)
  ├─ non-transactional side effect → write a `started` ledger row and commit BEFORE the call
  └─ handler in a savepoint with SET LOCAL statement_timeout; idempotent tools retried on transient faults
        (min(tool.max_attempts, task.max_retries + 1)); non-idempotent never retried; unknown outcome → unverified
     → write-once `tool_executions` row: status, attempts, output, evidence refs, approval request, duration
```
On *finish*, `validate()` checks deterministically: every action finished · every outcome known · nothing refused ·
needed integrations connected · **every number in the summary and findings appears in a tool result, the request or
the task** · the playbook's completion criteria. Final status: `failed` › `unverified` › `needs_review` › `completed`.
A failed task with `on_failure: escalate` records an automatic escalation.

## Run lifecycle (`orchestration/state.py`)
`queued → running → completed | needs_review | unverified | failed | blocked`, with `awaiting_approval` and
`waiting_children` returning to `queued`; `skipped` (overlapping run, daily limit) and `cancelled` from waiting states.
Claiming a run locks the run row and the agent row, so the overlap check (same `lock_key` running) and the
`max_runs_per_day` check (company-local day) can't race. A job retried after a crash resumes the same run: leftover
`started` rows become `unverified`, finished steps are read back from the ledger and never repeated.

## Triggers
- **On demand** — `POST /api/v1/workflows {agent_id, task_key | request}`; optional `Idempotency-Key` header.
- **Events** — business services call `orchestration.events.emit` inside the transaction that recorded the change
  (`invoice.created`, `payment.received`, `expense.submitted`); the scheduler emits `invoice.overdue` once per invoice.
  One run per (event, subject, agent, task). With a business-hours execution window the run is deferred
  (`not_before`) to the next opening.
- **Schedules** — `scheduler.tick()` (Celery beat every 60 s, or `python -m abos.jobs tick`): each occurrence that
  fell due in the last 15 minutes becomes one run keyed by the occurrence; deferred runs whose time came are released.
  Occurrences missed while the scheduler was down longer than that are not replayed.

## Tool registry (`tools/registry.py`, ADR-025)
Code-defined, versioned (`REGISTRY_VERSION`, recorded on every ledger row). Each tool: description, input schema
(Pydantic, `extra=forbid`) and output schema, scope (→ risk), validation rules, approval (`config` | `always`),
timeout, retry, idempotency, audit (`ledger` | `ledger+audit`). `GET /api/v1/tools` lists them.

| Tool | Scope | Notes |
|---|---|---|
| `knowledge.search` | data.read | retrieval with the agent's access levels + doc types; excerpts redacted |
| `escalate` | — | always allowed; audit event (delivery: Phase 6) |
| `invoices.read` | data.read | validated totals, balances, days overdue, aging, priority, discrepancy checks, last reminder |
| `expenses.read` | data.read | totals per currency; over-limit vs confirmed thresholds |
| `reminder.draft` | records.draft | fixed template filled with validated figures; refuses paid/void, discrepancies, a reminder sent < 7 days ago; reuses an identical open draft |
| `reminder.send` | comms.external | approval **always**, never retried; dev outbox = stored, not delivered (labelled); SMTP = `unverified` until delivery is confirmed |
| `reports.read`, `kpi.read` | data.read | execution records; objectives (no KPI measurements exist yet — said so) |
| `briefing.draft` | records.draft | a draft for the CEO |
| `agents.delegate` | data.read | Executive only; one level; delegated runs can't delegate |
Every other catalog tool (CRM, tickets, inventory, …) is registered as **not connected**: calls are recorded as
`unavailable` and reported as missing evidence.

## Delegation
The Executive agent's request playbook calls `agents.delegate` once: each other active agent gets a `delegated`
child run (depth 1) of its own read-only request task. The parent waits (`waiting_children`); the last child to
finish queues it again; it consolidates the children's verified summaries and lists every agent without a verified
result as missing evidence. No agent talks to another agent; runs only exchange stored results.

## Business records (`business/`)
Invoices (total computed from lines with exact `Decimal`, half-up to cents; an imported `recorded_total` that
disagrees is a discrepancy), payments (row-locked, never above the balance, unique bank reference per invoice),
expenses, drafts. `invoice_lines` and `payments` are insert-only for the app role. Permissions: `records.read`,
`records.manage` (manager+). Run details and the ledger need `records.read` (they quote records); the run list needs
`task.read`.

## What dev mode proves
With `llm_provider=dev` the playbooks plan; the runs prove governance, tools, evidence, idempotency, approvals and
validation on real records — not model judgement. The model planner path is tested with a fake client only.
