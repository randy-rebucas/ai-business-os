"""Workflow run state machine (explicit, enforced server-side — SPEC §3 step 7 'explicit workflow engine').

queued → running → completed | needs_review | unverified | failed | blocked
            ↘ awaiting_approval → queued (decision recorded) · waiting_children → queued (delegated runs finished)
queued → skipped (overlap, daily limit) | blocked (agent no longer allowed) | cancelled

- completed:    every step finished, every check passed, every figure in the output came from a tool result.
- needs_review: finished, but something needs a person: an action was refused or rejected, a tool isn't connected,
                a completion criterion wasn't met.
- unverified:   an outcome is unknown (e.g. a side effect timed out) — never reported as success (SPEC step 8).
- failed:       a step failed after its retries, or the run itself errored.
"""

from abos.core.errors import AppError

TRANSITIONS: dict[str, frozenset[str]] = {
    "queued": frozenset({"running", "skipped", "blocked", "cancelled"}),
    "running": frozenset({"awaiting_approval", "waiting_children", "completed", "needs_review", "unverified",
                          "failed", "blocked", "running"}),
    "awaiting_approval": frozenset({"queued", "cancelled"}),
    "waiting_children": frozenset({"queued", "cancelled"}),
    "completed": frozenset(), "needs_review": frozenset(), "unverified": frozenset(), "failed": frozenset(),
    "blocked": frozenset(), "cancelled": frozenset(), "skipped": frozenset(),
}
TERMINAL = frozenset(k for k, v in TRANSITIONS.items() if not v)
ACTIVE = frozenset({"queued", "running", "awaiting_approval", "waiting_children"})

LABELS = {
    "queued": "Queued", "running": "Running", "awaiting_approval": "Awaiting approval",
    "waiting_children": "Waiting for other agents", "completed": "Completed", "needs_review": "Needs review",
    "unverified": "Unverified", "failed": "Failed", "blocked": "Blocked", "cancelled": "Cancelled",
    "skipped": "Skipped",
}


def transition(run, target: str, reason: str | None = None) -> str:
    previous = run.status
    if target not in TRANSITIONS.get(previous, frozenset()):
        raise AppError(409, "invalid_transition", f"A {LABELS[previous].lower()} run can't become "
                                                  f"{LABELS[target].lower()}", {"from": previous, "to": target})
    run.status = target
    if reason is not None:
        run.status_reason = reason[:500]
    return previous
