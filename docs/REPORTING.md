# Reporting, notifications, Control Center, usage (Phase 6)

Implements SPEC §3 step 8. Code: `backend/abos/{reporting, notifications, usage, tools/reconcile.py}`. Pages:
`/app/control-center`, `/app/reports`, `/app/reports/[id]`, `/app/notifications` (inbox, preferences, delivery
log), `/app/usage`; agent profile tabs "Reports" and "Performance"; unread badge in the navigation.

## Daily reports (`reporting/service.py`, ADR-029)
One report per agent per company-local day, built deterministically from the runs created that day, their
`tool_executions`, `action_requests`, reconciliations, `model_usage` and the approved schedule — no model writes it.
The 15 SPEC sections: agent & period · assigned tasks · completed · in progress · failed · blocked/skipped · awaiting
approval (runs + pending actions) · actions performed (per tool: attempted / succeeded / unknown / failed / not run) ·
verified outcomes · evidence · exceptions & risks · escalations · upcoming (next occurrences + deferred runs) · KPIs
(platform-measured: completion, SLA, actions completed vs attempted; catalog KPIs are listed as "no measurement source
yet") · costs. Every item carries its run / execution / request ids, indexed in `report_evidence`.

- **Attempted vs completed vs unverified**: an execution that ran is attempted; only `succeeded`, or `unverified`
  later *confirmed* by a reconciliation, is completed; an unknown outcome stays unverified and is listed.
- **When**: `scheduler.tick` builds final reports for every finished local day of the last week (from activation on)
  and notifies `report.read` holders once. "Build today's report" (`POST /reports/generate`, `task.manage`) builds a
  labelled *so far* version; rebuilding bumps `version`.
- **Access**: list `report.read`; content `records.read` (it quotes run summaries and records).

## Reconciliation (`tools/reconcile.py`)
The ledger is never rewritten. A `reminder.send` handed to SMTP is `unverified`; when the mail outbox reports the
message `sent` or `failed`, an insert-only `execution_reconciliations` row records it (once). Dev-outbox sends are
stored, never delivered, and are not reconciled.

## Notifications (`notifications/`, ADR-030)
| Kind | Raised by | Severity | Recipients (permission) |
|---|---|---|---|
| action_required | an action request | warning | `approval.decide` |
| escalation | the `escalate` tool | normal→info, high→warning, critical→critical | `task.manage` |
| run_failed / run_unverified | a run finishing failed / unverified | warning / critical | `task.manage` |
| budget | a run skipped at the monthly budget | warning | `usage.read` |
| report_ready | a final daily report | info | `report.read` |

In-app always (deduplicated per event and person). Email immediately when severity ≥ the user's `email_immediate`
(default: critical); SMS for critical alerts when enabled with a number; everything not yet digested goes into one
daily digest at the user's `digest_time` in the company time zone. Deliveries: per-user limits (email/hour, SMS/day;
over the limit → `suppressed`, still in the digest), statuses `queued → handed_off → sent | failed → … | abandoned`,
`stored` for dev providers, exponential backoff retries (2, 4, 8… min) up to `notify_max_attempts`; handed-off emails
take their final status from the outbox. Channels sit behind one interface: email = `identity.mailer`; SMS =
`SmsProvider` (`dev` stores and is labelled, refused in production; `none` = not configured).

## Control Center (`reporting/dashboard.py`) and usage (`usage/service.py`, ADR-031)
Counts from records only, filtered by agent, department, run status, company-local date range and task priority:
agents by status; tasks run / completed / in progress / awaiting approval (+ pending actions) / over SLA / failed /
unverified / needs review / blocked; failed workflows; high and critical escalations; per-agent performance
(completion rate, failures, average duration, cost); usage cost; recent activity; upcoming work. "Over SLA" = a run
that took, or has been open, longer than its task's `sla_minutes`.

Usage: calls, tokens and estimated cost by agent, purpose and company-local day from `model_usage`; dev-adapter calls
are counted, cost nothing and are labelled. Budgets: an agent's approved `monthly_budget_usd` is enforced when a run is
claimed (month-to-date in the company time zone) — the run is `skipped` and `usage.read` holders are notified once a
month. The company budget is compared only when it is in USD.
