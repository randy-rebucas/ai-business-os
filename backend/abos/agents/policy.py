"""Code-defined vocabulary for agent governance (SPEC §3 step 5): permission scopes, risk, modes, events, operating
modes. Like `identity/permissions.py` this is the single place to read; agent scopes never inherit a human's role
(ADR-004). Configurations store scope *names*; validation checks them against this map and the definition ceilings.
"""

from typing import Literal

Mode = Literal["denied", "approval_required", "auto"]
MODE_ORDER = {"denied": 0, "approval_required": 1, "auto": 2}

Risk = Literal["low", "medium", "high", "critical"]

# scope -> (label, risk, highest mode any AI agent may ever hold). Critical scopes can never run unattended.
SCOPES: dict[str, tuple[str, Risk, Mode]] = {
    "data.read": ("Read business data", "low", "auto"),
    "records.draft": ("Create draft records", "low", "auto"),
    "records.modify": ("Modify permitted records", "medium", "auto"),
    "comms.external": ("Send external communications", "high", "auto"),
    "transactions.create": ("Create transactions", "high", "approval_required"),
    "transactions.approve": ("Approve transactions", "critical", "denied"),  # a human decision, always
    "finance.execute": ("Execute financial operations (payments, transfers)", "critical", "approval_required"),
    "documents.sensitive": ("Access restricted and confidential documents", "high", "auto"),
}

# What a scope needs before an approved, active agent may use it automatically (SPEC: "routine read-only tasks may
# execute automatically after activation; sensitive actions must require appropriate authorization").
DEFAULT_MODE: dict[str, Mode] = {
    "data.read": "auto",
    "records.draft": "auto",
    "records.modify": "approval_required",
    "comms.external": "approval_required",
    "transactions.create": "approval_required",
    "transactions.approve": "denied",
    "finance.execute": "denied",
    "documents.sensitive": "denied",
}

# Events an event-driven task may subscribe to. Phase 5 tools emit them; unknown names are rejected now.
EVENTS: dict[str, str] = {
    "invoice.overdue": "An invoice passes its due date",
    "invoice.created": "A new invoice is recorded",
    "payment.received": "A customer payment is recorded",
    "expense.submitted": "An expense is submitted for review",
    "lead.created": "A new sales lead arrives",
    "opportunity.stalled": "A sales opportunity has had no activity for its follow-up window",
    "ticket.created": "A new customer support ticket arrives",
    "ticket.escalated": "A support ticket is escalated or marked as a complaint",
    "stock.low": "A stock item falls below its reorder level",
    "purchase_order.received": "A purchase order delivery is recorded",
    "task.overdue": "An assigned task passes its deadline",
    "leave.requested": "An employee submits a leave request",
    "employee.onboarding": "A new employee starts onboarding",
    "campaign.ended": "A marketing campaign reaches its end date",
    "document.indexed": "A new company document is approved into the knowledge base",
}

OPERATING_MODES: dict[str, str] = {
    "always_on": "24/7 monitoring — responds to supported events and eligible tasks at any time",
    "business_hours": "Business hours — routine work only during the company's operating hours",
    "scheduled": "Scheduled execution — runs selected tasks at set times",
    "event_driven": "Event-driven — activates when a supported event occurs",
    "on_demand": "On demand — runs only when an authorised person asks",
}

AUTOMATION_LEVELS: dict[str, str] = {
    "observe": "Observe only — reads and reports, changes nothing",
    "draft": "Draft — prepares drafts for a person to review and send",
    "assisted": "Assisted — performs permitted actions, asks for approval on sensitive ones",
    "autonomous": "Autonomous — performs every permitted action without asking (sensitive scopes still need approval)",
}

# Scopes that change something outside the agent's own drafts. Observe-only agents hold none of them.
WRITE_SCOPES = ("records.modify", "comms.external", "transactions.create", "finance.execute")

DOC_TYPES = ("policy", "sop", "handbook", "catalog", "pricing", "contract", "financial", "org_chart",
             "job_description", "workflow", "script", "other")


def scope_label(scope: str) -> str:
    return SCOPES[scope][0]


def scope_risk(scope: str) -> Risk:
    return SCOPES[scope][1]


def platform_ceiling(scope: str) -> Mode:
    return SCOPES[scope][2]


def within(mode: str, ceiling: str) -> bool:
    return MODE_ORDER[mode] <= MODE_ORDER[ceiling]
