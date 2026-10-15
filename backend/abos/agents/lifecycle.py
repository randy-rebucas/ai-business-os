"""Agent lifecycle state machine (SPEC §3 step 2), enforced server-side.

available (catalog) → selected → configuring → awaiting_approval → testing → ready_for_deployment → active ⇄ paused
Any live state can fail or retire; retired is terminal. Editing an approved configuration sends the agent back to
configuring, so changed behaviour always needs a new approval.

Invariant checked here, not by callers: an agent can only be in testing / ready_for_deployment / active / paused
while its current configuration is the approved one. No endpoint can skip the CEO's approval.
"""

from datetime import UTC, datetime

from abos.agents.models import AgentInstance
from abos.core.errors import AppError

TRANSITIONS: dict[str, frozenset[str]] = {
    "selected": frozenset({"configuring", "retired"}),
    "configuring": frozenset({"awaiting_approval", "failed", "retired"}),
    "awaiting_approval": frozenset({"configuring", "testing", "retired"}),
    "testing": frozenset({"configuring", "ready_for_deployment", "failed", "retired"}),
    "ready_for_deployment": frozenset({"active", "configuring", "failed", "retired"}),
    "active": frozenset({"paused", "configuring", "failed", "retired"}),
    "paused": frozenset({"active", "configuring", "retired"}),
    "failed": frozenset({"configuring", "retired"}),
    "retired": frozenset(),
}

NEEDS_APPROVED_CONFIG = frozenset({"testing", "ready_for_deployment", "active", "paused"})

LABELS = {
    "available": "Available", "selected": "Selected", "configuring": "Configuring",
    "awaiting_approval": "Awaiting approval", "testing": "Testing", "ready_for_deployment": "Ready for deployment",
    "active": "Active", "paused": "Paused", "failed": "Failed", "retired": "Retired",
}


def can_transition(current: str, target: str) -> bool:
    return target in TRANSITIONS.get(current, frozenset())


def transition(instance: AgentInstance, target: str, reason: str | None = None) -> str:
    """Move `instance` to `target` or raise 409. Returns the previous status (for the audit record)."""
    previous = instance.status
    if previous == target:
        return previous
    if not can_transition(previous, target):
        raise AppError(409, "invalid_transition",
                       f"An agent that is {LABELS[previous].lower()} can't become {LABELS[target].lower()}",
                       {"from": previous, "to": target})
    if target in NEEDS_APPROVED_CONFIG and (instance.approved_config_id is None
                                            or instance.approved_config_id != instance.current_config_id):
        raise AppError(409, "approval_required", "The current configuration has not been approved",
                       {"from": previous, "to": target})
    instance.status = target
    instance.status_reason = (reason or "")[:300] or None
    instance.status_changed_at = datetime.now(UTC)
    return previous
