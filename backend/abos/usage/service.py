"""Usage & cost tracking and budgets (SPEC §3 step 8, §5). Source of truth: the `model_usage` ledger (every model and
embedding call, written even when the call failed) and the execution records. Costs are the gateway's estimates from
its price table; the provider invoice is authoritative. Dev adapter calls are counted but cost nothing — and are
labelled, so a zero is never mistaken for real spend.

Budgets: an agent's approved `limits.monthly_budget_usd` is enforced before every run (ADR-031) — once month-to-date
spend in the company's time zone reaches it, runs are skipped and the owners are told. The company budget is compared
only when it is set in USD (no exchange rates are invented, as ADR-020).
"""

import uuid
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from abos.agents.models import AgentConfiguration, AgentInstance
from abos.company import service as company
from abos.llm.models import ModelUsage
from abos.orchestration.models import WorkflowRun
from abos.tools.models import ToolExecution

CENTS = Decimal("0.0001")


def _tz(db: Session, org_id: uuid.UUID) -> ZoneInfo:
    tz = company.get_profile(db, org_id).timezone
    return ZoneInfo(tz) if tz else ZoneInfo("UTC")


def month_start(db: Session, org_id: uuid.UUID, now: datetime | None = None, *, zone: ZoneInfo | None = None) -> datetime:
    zone = zone or _tz(db, org_id)
    local = (now or datetime.now(UTC)).astimezone(zone)
    return datetime.combine(local.date().replace(day=1), time(0), zone).astimezone(UTC)


def spend(db: Session, org_id: uuid.UUID, *, since: datetime, until: datetime | None = None,
          instance_id: uuid.UUID | None = None) -> Decimal:
    stmt = select(func.coalesce(func.sum(ModelUsage.cost_usd), 0)).where(ModelUsage.organization_id == org_id,
                                                                          ModelUsage.created_at >= since)
    if until is not None:
        stmt = stmt.where(ModelUsage.created_at < until)
    if instance_id is not None:
        stmt = stmt.where(ModelUsage.agent_instance_id == instance_id)
    return Decimal(str(db.scalar(stmt))).quantize(CENTS)


def _budget(cfg: AgentConfiguration | None, spent: Decimal) -> dict:
    budget = Decimal(str(cfg.config["limits"]["monthly_budget_usd"])) if cfg else None
    over = budget is not None and spent >= budget and (budget > 0 or spent > 0)
    return {"budget_usd": str(budget) if budget is not None else None, "spent_usd": str(spent),
            "remaining_usd": str(max(budget - spent, Decimal(0))) if budget is not None else None, "over": over}


def _config_id(inst: AgentInstance) -> uuid.UUID | None:
    return inst.approved_config_id or inst.current_config_id


def agent_budget(db: Session, inst: AgentInstance) -> dict:
    cfg = db.get(AgentConfiguration, _config_id(inst)) if _config_id(inst) else None
    spent = spend(db, inst.organization_id, since=month_start(db, inst.organization_id), instance_id=inst.id)
    return _budget(cfg, spent)


def agent_budgets(db: Session, org_id: uuid.UUID, instances: list[AgentInstance], since: datetime) -> list[dict]:
    """`agent_budget` for many agents in three queries, whatever their number."""
    ids = [c for c in (_config_id(i) for i in instances) if c]
    configs = {c.id: c for c in db.scalars(select(AgentConfiguration).where(AgentConfiguration.id.in_(ids)))} \
        if ids else {}
    spent = dict(db.execute(select(ModelUsage.agent_instance_id, func.coalesce(func.sum(ModelUsage.cost_usd), 0))
                            .where(ModelUsage.organization_id == org_id, ModelUsage.created_at >= since,
                                   ModelUsage.agent_instance_id.in_([i.id for i in instances]))
                            .group_by(ModelUsage.agent_instance_id)).all()) if instances else {}
    return [{"instance_id": str(i.id), "agent": i.name,
             **_budget(configs.get(_config_id(i)), Decimal(str(spent.get(i.id, 0))).quantize(CENTS))}
            for i in instances]


def summary(db: Session, org_id: uuid.UUID, *, date_from: date, date_to: date) -> dict:
    zone = _tz(db, org_id)
    start = datetime.combine(date_from, time(0), zone).astimezone(UTC)
    end = datetime.combine(date_to + timedelta(days=1), time(0), zone).astimezone(UTC)
    rows = db.execute(select(ModelUsage.agent_instance_id, ModelUsage.purpose, ModelUsage.provider,
                             func.count(), func.sum(ModelUsage.input_tokens), func.sum(ModelUsage.output_tokens),
                             func.coalesce(func.sum(ModelUsage.cost_usd), 0),
                             func.count().filter(ModelUsage.status != "ok"))
                      .where(ModelUsage.organization_id == org_id, ModelUsage.created_at >= start,
                             ModelUsage.created_at < end)
                      .group_by(ModelUsage.agent_instance_id, ModelUsage.purpose, ModelUsage.provider)).all()
    instances = list(db.scalars(select(AgentInstance).where(AgentInstance.organization_id == org_id)
                                .order_by(AgentInstance.definition_key)))
    names = {i.id: i.name for i in instances}
    by_agent: dict[str, dict] = {}
    by_purpose: dict[str, dict] = {}
    total, calls, dev_calls, errors = Decimal(0), 0, 0, 0
    for inst_id, purpose, provider, n, tin, tout, cost, err in rows:
        cost = Decimal(str(cost))
        total, calls, errors = total + cost, calls + n, errors + err
        dev_calls += n if provider in ("dev", "hash") else 0
        key = str(inst_id) if inst_id else "none"
        a = by_agent.setdefault(key, {"instance_id": str(inst_id) if inst_id else None,
                                      "agent": names.get(inst_id, "Not an agent (people's requests, ingestion)"),
                                      "calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": Decimal(0)})
        a["calls"] += n
        a["input_tokens"] += tin or 0
        a["output_tokens"] += tout or 0
        a["cost_usd"] += cost
        p = by_purpose.setdefault(purpose, {"purpose": purpose, "calls": 0, "cost_usd": Decimal(0)})
        p["calls"] += n
        p["cost_usd"] += cost
    # Company-local calendar days, aggregated in SQL. The local day is computed once in a subquery and grouped by
    # its column: grouping by the expression itself fails, because each timezone() call binds its own parameter.
    local = select(func.date(func.timezone(str(zone), ModelUsage.created_at)).label("day"), ModelUsage.cost_usd) \
        .where(ModelUsage.organization_id == org_id, ModelUsage.created_at >= start,
               ModelUsage.created_at < end).subquery()
    daily = [(d, n, Decimal(str(c))) for d, n, c in db.execute(
        select(local.c.day, func.count(), func.coalesce(func.sum(local.c.cost_usd), 0))
        .group_by(local.c.day).order_by(local.c.day))]
    executions = db.scalar(select(func.count()).select_from(ToolExecution).where(
        ToolExecution.organization_id == org_id, ToolExecution.created_at >= start,
        ToolExecution.created_at < end)) or 0
    runs = db.scalar(select(func.count()).select_from(WorkflowRun).where(
        WorkflowRun.organization_id == org_id, WorkflowRun.created_at >= start, WorkflowRun.created_at < end)) or 0
    profile = company.get_profile(db, org_id)
    since = month_start(db, org_id, zone=zone)
    month_spend = spend(db, org_id, since=since)
    company_budget = None
    if profile.monthly_ai_budget is not None:
        comparable = (profile.budget_currency or "USD") == "USD"
        company_budget = {"amount": str(profile.monthly_ai_budget), "currency": profile.budget_currency or "USD",
                          "comparable": comparable, "spent_usd": str(month_spend),
                          "over": comparable and month_spend >= profile.monthly_ai_budget > 0}
    budgets = agent_budgets(db, org_id, [i for i in instances if i.status != "retired"], since)
    q = lambda v: str(Decimal(v).quantize(CENTS))  # noqa: E731
    return {
        "from": date_from.isoformat(), "to": date_to.isoformat(), "timezone": str(zone),
        "total_cost_usd": q(total), "calls": calls, "errors": errors, "dev_calls": dev_calls,
        "dev_label": ("Development adapters (no AI model called) — these calls cost nothing" if dev_calls else None),
        "runs": runs, "tool_executions": executions,
        "by_agent": sorted(({**a, "cost_usd": q(a["cost_usd"])} for a in by_agent.values()),
                           key=lambda a: a["agent"]),
        "by_purpose": sorted(({**p, "cost_usd": q(p["cost_usd"])} for p in by_purpose.values()),
                             key=lambda p: -p["calls"]),
        "daily": [{"date": d.isoformat(), "calls": n, "cost_usd": q(c)} for d, n, c in daily],
        "month_to_date_usd": str(month_spend), "company_budget": company_budget, "agent_budgets": budgets,
        "note": "Costs are estimates from the gateway's price table; the provider's invoice is authoritative.",
    }
