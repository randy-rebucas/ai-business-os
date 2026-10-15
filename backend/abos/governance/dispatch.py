"""The governance dispatcher: the one decision path every tool call takes (SPEC §3 steps 6–7, ADR-022, ADR-025).

Shared by the simulation sandbox (fixture tools) and real execution (`orchestration`), so what a readiness run proves
about a configuration is exactly what governs live work. Given a valid call it answers executed | blocked |
held_for_approval, in this order:

1. escalation is always allowed;
2. the agent is authorised for the tool and the tool's scope is not denied (permission enforcement);
3. the deployment stage allows the scope (observation = read + drafts only, everything else waits for a person);
4. money actions above a confirmed business-rule threshold — or with no confirmed limit at all — wait for approval;
5. scopes set to "approval required", and side effects of tasks marked as needing approval, wait for approval.

Input validation (`validate_input`) runs before it; idempotency, retries and tenancy are the caller's job, because
they differ between fixtures and real records. This module never touches the database.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from abos.agents import policy

SIDE_EFFECT_SCOPES = ("records.modify", "comms.external", "transactions.create", "finance.execute",
                      "transactions.approve")
OBSERVATION_SCOPES = ("data.read", "records.draft")


@dataclass
class Threshold:
    amount: Decimal
    currency: str
    rule_id: str
    statement: str


# ---- input validation (the generic shape rules; real tools add their own Pydantic schema) -----------------------

def kind(tool: str, scope: str | None) -> str:
    if tool == "escalate":
        return "escalate"
    if tool == "knowledge.search":
        return "search"
    if scope in ("finance.execute", "transactions.create", "transactions.approve"):
        return "money"
    if scope == "records.modify":
        return "update"
    if scope == "comms.external":
        return "send"
    if scope == "records.draft":
        return "draft"
    return "read"


REQUIRED = {"escalate": ("reason",), "search": ("query",), "money": ("amount", "currency", "reference"),
            "update": ("id", "changes"), "send": ("recipient", "body"), "draft": ("subject", "body"), "read": ()}


def validate_input(tool: str, scope: str | None, data: Any) -> str | None:
    if not isinstance(data, dict):
        return "input must be an object"
    for f in REQUIRED[kind(tool, scope)]:
        v = data.get(f)
        if v is None or (isinstance(v, str) and not v.strip()):
            return f"missing {f}"
    return validate_money(data) or (
        "changes must be an object" if kind(tool, scope) == "update" and not isinstance(data.get("changes"), dict)
        else None)


def validate_money(data: dict) -> str | None:
    if "amount" in data:
        try:
            if Decimal(str(data["amount"])) < 0:
                return "amount must not be negative"
        except InvalidOperation:
            return "amount must be a number"
    if "currency" in data and not (isinstance(data["currency"], str) and len(data["currency"]) == 3):
        return "currency must be a 3-letter code"
    return None


# ---- the decision ------------------------------------------------------------------------------------------------

def decide(*, tool: str, label: str, scope: str | None, platform: bool, data: dict, config: dict,
           stage: str | None, task: dict | None, thresholds: list[Threshold]) -> tuple[str, str]:
    """(decision, reason) for a valid call before execution: executed | blocked | held_for_approval.

    `stage` None evaluates the configuration as approved (simulation); a live agent passes its deployment stage."""
    if scope is None:  # escalation is always allowed
        return "executed", "Escalation is always allowed"
    mode = config["permissions"].get(scope, "denied")
    if not platform and tool not in config["job"]["authorized_tools"]:
        return "blocked", f"\"{label}\" is not an authorised tool for this agent"
    if mode == "denied":
        return "blocked", f"Permission \"{policy.scope_label(scope)}\" is denied"
    if stage == "observation" and scope not in OBSERVATION_SCOPES:
        return "held_for_approval", "Observation stage: only reading and drafting run automatically"
    if scope in SIDE_EFFECT_SCOPES and "amount" in data:
        amount, currency = Decimal(str(data["amount"])), str(data.get("currency", "")).upper()
        limits = [t for t in thresholds if t.currency == currency]
        if not limits:
            return "held_for_approval", f"No confirmed limit for {currency} amounts; a person must approve"
        limit = min(limits, key=lambda t: t.amount)
        if amount > limit.amount:
            return "held_for_approval", f"{amount} {currency} exceeds the confirmed limit of {limit.amount} " \
                                        f"{currency} (rule: {limit.statement[:120]})"
    if mode == "approval_required":
        return "held_for_approval", f"Permission \"{policy.scope_label(scope)}\" requires approval"
    if task and task.get("approval_required") and scope in SIDE_EFFECT_SCOPES:
        return "held_for_approval", f"Task \"{task['title']}\" requires approval"
    return "executed", "Allowed by the approved configuration"
