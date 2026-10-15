"""The agent tool registry (SPEC §3 step 7 'Tool execution', ADR-025). Code-defined, like permission scopes.

Every tool has a name, description, input and output schema (Pydantic → JSON Schema), required permission scope,
validation rules, risk (from the scope), approval requirement, timeout, retry policy and audit requirement. A plan can
only name tools in this registry; there is no tool for SQL, shell, HTTP or anything not listed. Catalog tools whose
integration doesn't exist yet are registered as *not connected*: a call to them is recorded and refused, never faked.

Approval: "config" = the dispatcher decides from the agent's approved configuration (scope mode, stage, thresholds,
task flags); "always" = every call needs a person's approval of its exact parameters, whatever the configuration
says (external side effects in this release).
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

from abos.agents import policy
from abos.governance import dispatch
from abos.tools import handlers as h

REGISTRY_VERSION = "tools-2026.10.1"

Period = Annotated[str, StringConstraints(pattern=r"^20\d\d-(0[1-9]|1[0-2])$")]


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SearchIn(_In):
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class EscalateIn(_In):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    severity: Literal["normal", "high", "critical"] = "normal"
    subject: Annotated[str, StringConstraints(max_length=200)] | None = None


class InvoicesReadIn(_In):
    invoice_id: uuid.UUID | None = None
    number: Annotated[str, StringConstraints(max_length=40)] | None = None
    state: Literal["all", "outstanding", "overdue", "paid", "void"] = "outstanding"
    period: Period | None = None
    limit: Annotated[int, Field(ge=1, le=200)] = 100


class ExpensesReadIn(_In):
    expense_id: uuid.UUID | None = None
    status: Literal["submitted", "approved", "rejected"] | None = None
    period: Period | None = None
    limit: Annotated[int, Field(ge=1, le=200)] = 100


class ReminderDraftIn(_In):
    invoice_id: uuid.UUID


class ReminderSendIn(_In):
    draft_id: uuid.UUID


class ReportsReadIn(_In):
    since_hours: Annotated[int, Field(ge=1, le=168)] = 24


class KpiReadIn(_In):
    pass


class BriefingDraftIn(_In):
    subject: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
    body: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20000)]


class DelegateIn(_In):
    request: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    agents: Annotated[list[str], Field(max_length=7)] = []


class AnyIn(BaseModel):
    """Not-connected tools: only the generic shape rules apply (they never run)."""

    model_config = ConfigDict(extra="allow")


@dataclass(frozen=True)
class ToolDef:
    key: str
    label: str
    description: str
    scope: str | None                       # None = escalation (always allowed)
    input: type[BaseModel]
    output: dict[str, Any]                  # JSON Schema of the output (documented, checked in tests)
    handler: Callable[..., h.ToolResult] | None
    validation: tuple[str, ...] = ()
    platform: bool = False                  # every agent has it, subject to its scopes
    approval: Literal["config", "always"] = "config"
    timeout_seconds: int = 10
    max_attempts: int = 2                   # automatic attempts for transient faults (idempotent tools only)
    idempotent: bool = True                 # safe to retry; non-idempotent calls are never retried automatically
    transactional: bool = True              # its effect commits atomically with its ledger row
    audit: Literal["ledger", "ledger+audit"] = "ledger"
    parameters: Callable[..., dict] | None = None  # resolves the exact action an approver reviews
    unavailable: str | None = None          # why it can't run (integration not connected)
    agents: tuple[str, ...] = field(default=())  # for platform tools limited to some catalog agents

    @property
    def risk(self) -> str:
        return policy.scope_risk(self.scope) if self.scope else "low"

    @property
    def side_effect(self) -> bool:
        return self.scope not in (None, "data.read")

    def describe(self) -> dict[str, Any]:
        return {"key": self.key, "label": self.label, "description": self.description, "scope": self.scope,
                "scope_label": policy.scope_label(self.scope) if self.scope else "Always allowed", "risk": self.risk,
                "input_schema": self.input.model_json_schema(), "output_schema": self.output,
                "validation": list(self.validation), "approval": self.approval,
                "timeout_seconds": self.timeout_seconds,
                "retry": {"max_attempts": self.max_attempts if self.idempotent else 1,
                          "on": ["timeout", "connection"] if self.idempotent else []},
                "idempotency": "per trigger" if self.side_effect else "not needed (read-only)",
                "audit": self.audit, "available": self.unavailable is None, "unavailable_reason": self.unavailable,
                "platform": self.platform}


def _obj(**props: str) -> dict[str, Any]:
    return {"type": "object", "properties": {k: {"type": v} for k, v in props.items()}}


_IMPLEMENTED: dict[str, ToolDef] = {t.key: t for t in (
    ToolDef("knowledge.search", "Search approved company knowledge",
            "Hybrid search over the workspace's indexed documents, filtered in SQL by the agent's access levels and "
            "then by its document types. Instruction-like text is redacted from excerpts.",
            "data.read", SearchIn, _obj(count="integer", sources="array", redactions="integer"), h.knowledge_search,
            ("Only indexed, current documents", "Access levels and document types from the approved configuration"),
            platform=True, timeout_seconds=20),
    ToolDef("escalate", "Escalate to a person",
            "Records an escalation with its reason and severity for the CEO (notification delivery: Phase 6).",
            None, EscalateIn, _obj(escalated="boolean", severity="string"), h.escalate,
            ("A reason is required",), platform=True, audit="ledger+audit"),
    ToolDef("invoices.read", "Read invoices and receivables",
            "Invoices with validated totals, payments, balances, days overdue, aging and follow-up priority, plus "
            "discrepancy checks (stated total vs lines).", "data.read", InvoicesReadIn,
            _obj(as_of="string", count="integer", invoices="array", outstanding_by_currency="object",
                 validated_checks="array"), h.invoices_read,
            ("This workspace's invoices only", "Figures computed with exact decimal arithmetic",
             "Amounts in different currencies are never added together")),
    ToolDef("expenses.read", "Read expenses",
            "Expenses with totals per currency and those above a confirmed business-rule limit.", "data.read",
            ExpensesReadIn, _obj(count="integer", expenses="array", totals_by_currency="object", over_limit="array"),
            h.expenses_read, ("Limits come only from confirmed business rules",)),
    ToolDef("reminder.draft", "Draft payment reminders",
            "Drafts a payment reminder for one outstanding invoice from a fixed template filled with the invoice's "
            "validated figures. Drafting never sends anything.", "records.draft", ReminderDraftIn,
            _obj(draft_id="string", subject="string", recipient="string", reused_existing="boolean"),
            h.reminder_draft,
            ("The invoice must be outstanding", "No reminder for an invoice with a discrepancy",
             f"At most one reminder per invoice every {h.REMINDER_GAP_DAYS} days",
             "An identical open draft is reused, not duplicated")),
    ToolDef("reminder.send", "Send approved payment reminders",
            "Sends one drafted reminder to the invoice's customer email through the mail adapter. Every send needs a "
            "person's approval of the exact recipient and text.", "comms.external", ReminderSendIn,
            _obj(sent_to="string", draft_id="string", delivery="object"), h.reminder_send,
            ("The draft must still be a draft", "The invoice must still be outstanding",
             "A changed draft or policy needs a new approval"),
            approval="always", idempotent=False, max_attempts=1, audit="ledger+audit",
            parameters=h.reminder_send_parameters),
    ToolDef("reports.read", "Read agent reports and execution records",
            "Workflow runs of the workspace in a time window, with status counts and escalations.", "data.read",
            ReportsReadIn, _obj(runs="integer", by_status="object", escalations="integer", items="array"),
            h.reports_read, ("Execution records only — no other agent's private data",)),
    ToolDef("kpi.read", "Read objective and KPI records",
            "Active business objectives with their KPI targets.", "data.read", KpiReadIn,
            _obj(count="integer", objectives="array", measurements="array"), h.kpi_read),
    ToolDef("briefing.draft", "Draft executive briefings",
            "Saves a briefing as a draft for the CEO.", "records.draft", BriefingDraftIn,
            _obj(draft_id="string", subject="string"), h.briefing_draft),
    ToolDef("agents.delegate", "Delegate analysis to other agents",
            "The Executive agent asks other active agents to work on a request; each runs its own read-only request "
            "task and the results come back for consolidation. One level only: delegated runs can't delegate.",
            "data.read", DelegateIn, _obj(children="array"), None,  # executed by the orchestrator (needs runs)
            ("Only active agents", "Delegated runs can't delegate further", "At most 7 agents"),
            platform=True, agents=("executive",)),
)}


def _not_connected(t: dict) -> ToolDef:
    return ToolDef(t["key"], t["label"], f"{t['label']}. The integration this tool needs isn't connected yet.",
                   t["scope"], AnyIn, {"type": "object"}, None,
                   unavailable="Integration not connected yet; the call is recorded, not run")


def tools_for(spec: dict) -> dict[str, ToolDef]:
    """The tools one agent's plans may name: platform tools + its catalog tools (implemented or not connected)."""
    out = {k: t for k, t in _IMPLEMENTED.items() if t.platform and (not t.agents or spec["key"] in t.agents)}
    for t in spec.get("tools", []):
        out[t["key"]] = _IMPLEMENTED.get(t["key"]) or _not_connected(t)
    return out


def all_tools(specs: list[dict]) -> list[ToolDef]:
    seen: dict[str, ToolDef] = {k: t for k, t in _IMPLEMENTED.items() if t.platform}
    for spec in specs:
        seen |= tools_for(spec)
    return sorted(seen.values(), key=lambda t: (t.unavailable is not None, t.key))


def validate(tool: ToolDef, data: Any) -> tuple[BaseModel | None, str | None]:
    """Shape rules shared with the simulation (dispatch.validate_input), then the tool's own schema."""
    if problem := dispatch.validate_input(tool.key, tool.scope, data) if tool.unavailable else None:
        return None, problem
    if not isinstance(data, dict):
        return None, "input must be an object"
    try:
        return tool.input.model_validate(data), None
    except ValidationError as exc:
        e = exc.errors()[0]
        where = ".".join(str(x) for x in e["loc"]) or "input"
        return None, f"{where}: {e['msg']}"[:300]
