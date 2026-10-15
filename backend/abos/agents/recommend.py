"""Recommended team (SPEC §3 step 2): deterministic rules over the company profile, documents and budget.

Each catalog definition declares signals (department names, software categories, challenge/objective keywords …).
Matches add weighted points and a human-readable reason; a score ≥ THRESHOLD recommends the agent. The Executive
agent is recommended once two others are, since it coordinates them. With a USD budget, the lowest-scoring agents
are dropped until the estimate fits. No model is involved, so the same profile always gets the same answer and every
recommendation can show why.
"""

import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from abos.agents.models import AgentDefinition, AgentInstance
from abos.agents.schemas import RecommendationItem, RecommendationOut
from abos.company import service as company
from abos.company.models import (
    BusinessObjective,
    BusinessProcess,
    Department,
    JobRole,
    Offering,
    OperationalChallenge,
    SoftwareSystem,
)
from abos.knowledge.models import Document

THRESHOLD = 2
WEIGHT = {"department": 2, "role": 1, "software": 2, "challenge_high": 3, "challenge": 2, "objective": 1,
          "documents": 1, "offerings": 1, "processes": 1, "employees": 2}
SIZE_MIN_EMPLOYEES = {"1": 1, "2-10": 2, "11-50": 11, "51-200": 51, "201-1000": 201, "1000+": 1000}


def _has(text: str | None, keywords: list[str]) -> str | None:
    low = (text or "").lower()
    return next((k for k in keywords if k in low), None)


def current_definitions(db: Session) -> list[AgentDefinition]:
    return list(db.scalars(select(AgentDefinition).where(AgentDefinition.is_current.is_(True))
                           .order_by(AgentDefinition.letter)))


def recommend(db: Session, org_id: uuid.UUID) -> RecommendationOut:
    profile = company.get_profile(db, org_id)

    def rows(model):
        return list(db.scalars(select(model).where(model.organization_id == org_id)))

    departments, roles, software = rows(Department), rows(JobRole), rows(SoftwareSystem)
    challenges, objectives, processes, offerings = (rows(OperationalChallenge), rows(BusinessObjective),
                                                    rows(BusinessProcess), rows(Offering))
    doc_types = {r[0]: r[1] for r in db.execute(
        select(Document.doc_type, func.count()).where(Document.organization_id == org_id, Document.status == "indexed")
        .group_by(Document.doc_type))}
    employees = profile.employee_count or SIZE_MIN_EMPLOYEES.get(profile.company_size or "", 0)
    hired = set(db.scalars(select(AgentInstance.definition_key).where(AgentInstance.organization_id == org_id,
                                                                      AgentInstance.status != "retired")))

    scored: dict[str, tuple[int, list[str]]] = {}
    definitions = current_definitions(db)
    for d in definitions:
        sig = d.spec.get("signals", {})
        score, reasons = 0, []
        if kws := sig.get("departments"):
            for dep in departments:
                if _has(dep.name, kws):
                    score += WEIGHT["department"]
                    reasons.append(f"Department: {dep.name}")
            for role in roles:
                if _has(role.title, kws):
                    score += WEIGHT["role"]
                    reasons.append(f"Job role: {role.title}")
        for sw in software:
            if sw.category in sig.get("software", []):
                score += WEIGHT["software"]
                reasons.append(f"Software: {sw.name} ({sw.category.replace('_', ' ')})")
        if kws := sig.get("challenges"):
            for c in challenges:
                if _has(f"{c.title} {c.description or ''}", kws):
                    score += WEIGHT["challenge_high"] if c.severity == "high" else WEIGHT["challenge"]
                    reasons.append(f"Challenge: {c.title} ({c.severity})")
        if kws := sig.get("objectives"):
            for o in objectives:
                if o.status == "active" and _has(f"{o.title} {o.kpi_name or ''}", kws):
                    score += WEIGHT["objective"]
                    reasons.append(f"Objective: {o.title}")
        for t in sig.get("doc_types", []):
            if doc_types.get(t):
                score += WEIGHT["documents"]
                reasons.append(f"{doc_types[t]} approved {t.replace('_', ' ')} document(s)")
        if sig.get("product_offerings") and any(o.kind == "product" for o in offerings):
            score += WEIGHT["offerings"]
            reasons.append("Sells physical products")
        if (n := sig.get("min_processes")) and len(processes) >= n:
            score += WEIGHT["processes"]
            reasons.append(f"{len(processes)} documented business processes")
        if (n := sig.get("min_employees")) and employees >= n:
            score += WEIGHT["employees"]
            reasons.append(f"About {employees}+ employees")
        scored[d.key] = (score, reasons)

    recommended = {k for k, (s, _) in scored.items() if s >= THRESHOLD and k != "executive"}
    exec_def = next((d for d in definitions if d.key == "executive"), None)
    if exec_def and len(recommended) >= exec_def.spec.get("signals", {}).get("min_other_agents", 2):
        recommended.add("executive")
        scored["executive"] = (scored["executive"][0] + THRESHOLD,
                               scored["executive"][1] + [f"Coordinates the {len(recommended) - 1} other recommended agents"])

    cost = {d.key: Decimal(d.spec["default_monthly_budget_usd"]) for d in definitions}
    excluded: dict[str, str] = {}
    budget = {"amount": profile.monthly_ai_budget, "currency": profile.budget_currency, "status": "not_set",
              "message": "No monthly AI workforce budget is set; estimates are not checked against a budget."}
    if profile.monthly_ai_budget is not None:
        if profile.budget_currency != "USD":
            budget |= {"status": "not_comparable",
                       "message": f"Your budget is in {profile.budget_currency}; agent estimates are in USD and no "
                                  "exchange rate is applied. Compare them yourself."}
        else:
            limit = profile.monthly_ai_budget
            # Drop the weakest first; the executive goes first among ties since it only coordinates.
            order = sorted(recommended, key=lambda k: (scored[k][0], k != "executive"))
            while order and sum(cost[k] for k in recommended) > limit:
                k = order.pop(0)
                recommended.discard(k)
                excluded[k] = f"Left out to stay within the ${limit:,.2f}/month budget"
            budget |= {"status": "within" if sum(cost[k] for k in recommended) <= limit else "over",
                       "message": f"Estimated cost fits the ${limit:,.2f}/month budget." if not excluded else
                       f"{len(excluded)} agent(s) left out to fit the ${limit:,.2f}/month budget."}

    items = [RecommendationItem(key=d.key, name=d.name, letter=d.letter, score=scored[d.key][0],
                                recommended=d.key in recommended, reasons=scored[d.key][1],
                                excluded_reason=excluded.get(d.key), estimated_monthly_usd=cost[d.key],
                                hired=d.key in hired) for d in definitions]
    items.sort(key=lambda i: (not i.recommended, -i.score, i.letter))
    section_status = {s.key: s.status for s in company.completeness(db, org_id).sections}
    gaps = [label for key, label in (("structure", "departments"), ("software", "software you use"),
                                     ("challenges", "operational challenges"), ("objectives", "objectives"),
                                     ("budget", "monthly AI budget")) if section_status[key] != "complete"]
    return RecommendationOut(items=items, recommended_keys=[i.key for i in items if i.recommended],
                             total_estimated_monthly_usd=sum((cost[k] for k in recommended), Decimal(0)),
                             budget=budget, profile_gaps=gaps,
                             method="Rules over your profile, documents and budget — no AI model involved.")
