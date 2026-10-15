"""Context-aware configuration checks (SPEC §9 'agent configuration validation'). Pure: callers load the context.

Errors block submission for approval; warnings are shown to the CEO but don't block. Permission ceilings are errors
because they are security boundaries: the platform ceiling (critical scopes never run unattended) and the catalog
definition's ceiling (e.g. a Finance agent can never execute payments).
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from abos.agents import policy
from abos.agents.schedule import outside_hours
from abos.agents.schemas import AgentConfig, Issue, TaskIn

DAY_LABEL = {"mon": "Mon", "tue": "Tue", "wed": "Wed", "thu": "Thu", "fri": "Fri", "sat": "Sat", "sun": "Sun"}


@dataclass
class Context:
    spec: dict[str, Any]                       # catalog definition
    timezone: str | None
    operating_schedule: dict[str, Any] | None
    company_budget: Decimal | None = None
    company_currency: str = "USD"
    other_agents_budget: Decimal = Decimal(0)  # other live agents' current monthly budgets
    confirmed_rule_ids: set[str] = field(default_factory=set)


def _cycle(tasks: list[TaskIn]) -> list[str] | None:
    graph = {t.key: [d for d in t.depends_on] for t in tasks}
    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(k: str) -> list[str] | None:
        state[k] = 1
        stack.append(k)
        for d in graph.get(k, []):
            if d not in graph:
                continue
            if state.get(d) == 1:
                return stack[stack.index(d):] + [d]
            if state.get(d) is None and (found := visit(d)):
                return found
        stack.pop()
        state[k] = 2
        return None

    for k in graph:
        if state.get(k) is None and (found := visit(k)):
            return found
    return None


def check(config: AgentConfig, tasks: list[TaskIn], ctx: Context) -> list[Issue]:
    out: list[Issue] = []

    def err(f: str, m: str) -> None:
        out.append(Issue(severity="error", field=f, message=m))

    def warn(f: str, m: str) -> None:
        out.append(Issue(severity="warning", field=f, message=m))

    ceilings: dict[str, str] = ctx.spec["permission_ceilings"]
    perms = config.permissions

    # -- permissions: platform and definition ceilings ------------------------------------------------------------
    for scope, mode in perms.items():
        label = policy.scope_label(scope)
        if not policy.within(mode, policy.platform_ceiling(scope)):
            err(f"permissions.{scope}", f"\"{label}\" can never be {mode.replace('_', ' ')} for an AI employee")
        elif not policy.within(mode, ceilings.get(scope, "denied")):
            err(f"permissions.{scope}", f"The {ctx.spec['name']} may hold \"{label}\" at most as "
                f"{ceilings.get(scope, 'denied').replace('_', ' ')}")
    if config.automation_level == "observe" and any(perms[s] != "denied" for s in policy.WRITE_SCOPES):
        warn("automation_level", "Observe-only agents normally hold no write permissions; deny them or raise the "
             "automation level")

    tools = {t["key"]: t for t in ctx.spec.get("tools", [])}
    for key in config.job.authorized_tools:
        if key not in tools:
            err("job.authorized_tools", f"Unknown tool \"{key}\" for this agent")
        elif perms[tools[key]["scope"]] == "denied":
            needed = policy.scope_label(tools[key]["scope"])
            err("job.authorized_tools", f"Tool \"{tools[key]['label']}\" needs the \"{needed}\" permission, which "
                "is denied")

    if set(config.knowledge.access_levels) - {"general"} and perms["documents.sensitive"] == "denied":
        err("knowledge.access_levels", "Restricted or confidential documents need the \"Access restricted and "
            "confidential documents\" permission")
    if not config.knowledge.doc_types:
        warn("knowledge.doc_types", "No document types selected: the agent can't use company knowledge")

    # -- operating schedule ----------------------------------------------------------------------------------------
    op = config.operating
    needs_hours = op.mode == "business_hours" or op.execution_window == "business_hours" \
        or op.monitoring == "business_hours"
    has_schedule_tasks = any(t.trigger.type == "schedule" for t in tasks)
    if (needs_hours or has_schedule_tasks) and not ctx.timezone:
        err("operating", "Set the company time zone (Company profile → Operating hours) before scheduling work")
    if needs_hours and not ctx.operating_schedule:
        err("operating", "Business-hours operation needs the company's operating days and hours")
    if op.mode == "always_on" and op.monitoring != "continuous":
        warn("operating.monitoring", "24/7 monitoring mode normally monitors continuously")

    # -- tasks -----------------------------------------------------------------------------------------------------
    keys = [t.key for t in tasks]
    dupes = sorted({k for k in keys if keys.count(k) > 1})
    if dupes:
        err("tasks", f"Duplicate task keys: {', '.join(dupes)}")
    if not tasks:
        warn("tasks", "No tasks: the agent will only act when asked")
    known = set(keys)
    supported = set(ctx.spec.get("supported_events", []))
    for i, t in enumerate(tasks):
        f = f"tasks[{i}]"
        for d in t.depends_on:
            if d == t.key:
                err(f"{f}.depends_on", f"\"{t.title}\" can't depend on itself")
            elif d not in known:
                err(f"{f}.depends_on", f"\"{t.title}\" depends on an unknown task \"{d}\"")
        for scope in t.required_permissions:
            if perms[scope] == "denied":
                err(f"{f}.required_permissions", f"\"{t.title}\" needs \"{policy.scope_label(scope)}\", which is denied")
            elif perms[scope] == "approval_required" and not t.approval_required:
                err(f"{f}.approval_required", f"\"{t.title}\" uses \"{policy.scope_label(scope)}\", which needs "
                    "approval — mark the task as requiring approval")
        if t.trigger.type == "event" and t.trigger.event not in supported:
            err(f"{f}.trigger", f"The {ctx.spec['name']} can't react to \"{t.trigger.event}\"")
        if t.trigger.type == "schedule" and op.execution_window == "business_hours" and ctx.operating_schedule:
            bad = outside_hours(t.trigger.schedule.model_dump(), ctx.operating_schedule)
            if bad:
                err(f"{f}.trigger", f"\"{t.title}\" runs at {t.trigger.schedule.time} on "
                    f"{', '.join(DAY_LABEL[d] for d in bad)}, outside business hours")
        for ref in t.policy_refs:
            if str(ref) not in ctx.confirmed_rule_ids:
                err(f"{f}.policy_refs", f"\"{t.title}\" cites a business rule that isn't confirmed")
        if op.mode == "on_demand" and t.trigger.type != "on_demand":
            warn(f"{f}.trigger", f"\"{t.title}\" won't run automatically in on-demand mode")
        elif op.mode == "scheduled" and t.trigger.type == "event":
            warn(f"{f}.trigger", f"\"{t.title}\" is event-driven but the agent runs in scheduled mode")
        elif op.mode == "event_driven" and t.trigger.type == "schedule":
            warn(f"{f}.trigger", f"\"{t.title}\" is scheduled but the agent runs in event-driven mode")
    if cycle := _cycle(tasks):
        err("tasks", f"Task dependencies form a cycle: {' → '.join(cycle)}")

    # -- budget ----------------------------------------------------------------------------------------------------
    if ctx.company_budget is not None and ctx.company_currency == "USD":
        total = ctx.other_agents_budget + config.limits.monthly_budget_usd
        if total > ctx.company_budget:
            warn("limits.monthly_budget_usd", f"All agents together would budget ${total:,.2f}/month, above the "
                 f"company's AI workforce budget of ${ctx.company_budget:,.2f}")
    return out


def has_errors(issues: list[Issue]) -> bool:
    return any(i.severity == "error" for i in issues)
