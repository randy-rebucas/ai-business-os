import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from abos.agents import service as agents
from abos.agents.schemas import ApprovalOut, ConfigOut
from abos.core.db import get_db
from abos.core.errors import AppError
from abos.governance import approvals, rules
from abos.governance import schemas as s
from abos.identity.deps import OrgContext, ai_work, require_org_permission
from abos.llm import gateway

rules_router = APIRouter(prefix="/api/v1/rules", tags=["governance"])
approvals_router = APIRouter(prefix="/api/v1/approvals", tags=["governance"])

REVIEW = require_org_permission("rule.review")


def _out(db: Session, items) -> list[s.RuleOut]:
    stale = rules.staleness(db, items)
    return [s.RuleOut.model_validate(r).model_copy(update={"stale": stale.get(r.id)}) for r in items]


# ---- business rules --------------------------------------------------------------------------------------------

@rules_router.get("", response_model=list[s.RuleOut])
def list_rules(status: str | None = Query(None, max_length=20),
               ctx: OrgContext = Depends(require_org_permission("knowledge.read")), db: Session = Depends(get_db)):
    return _out(db, rules.list_rules(db, ctx, status))


@rules_router.post("/extract", response_model=s.ExtractOut, dependencies=[ai_work()])
def extract(ctx: OrgContext = Depends(REVIEW), db: Session = Depends(get_db)):
    try:
        report = rules.extract(db, ctx)
    except gateway.LLMError as exc:
        raise AppError(502 if exc.code != "not_configured" else 503, f"ai_{exc.code}", str(exc)) from exc
    return s.ExtractOut(**report.__dict__)


@rules_router.post("", response_model=s.RuleOut, status_code=201)
def create_rule(data: s.RuleCreateIn, ctx: OrgContext = Depends(REVIEW), db: Session = Depends(get_db)):
    rule = rules.create_manual(db, ctx, title=data.title, statement=data.statement, kind=data.kind,
                               rule_applies_to=list(data.applies_to))
    return _out(db, [rule])[0]


@rules_router.post("/{rule_id}/review", response_model=s.RuleOut)
def review_rule(rule_id: uuid.UUID, data: s.RuleReviewIn, ctx: OrgContext = Depends(REVIEW),
                db: Session = Depends(get_db)):
    rule = rules.review(db, ctx, rules.get(db, ctx, rule_id), data.decision, resolution=data.resolution,
                        statement=data.statement,
                        rule_applies_to=list(data.applies_to) if data.applies_to is not None else None)
    return _out(db, [rule])[0]


# ---- approvals -------------------------------------------------------------------------------------------------

@approvals_router.get("/pending", response_model=list[s.PendingOut])
def pending(ctx: OrgContext = Depends(require_org_permission("agent.read")), db: Session = Depends(get_db)):
    return approvals.pending(db, ctx)


@approvals_router.get("", response_model=list[ApprovalOut])
def history(limit: int = Query(100, ge=1, le=200), ctx: OrgContext = Depends(require_org_permission("agent.read")),
            db: Session = Depends(get_db)):
    return approvals.history(db, ctx, limit)


@approvals_router.get("/configurations/{config_id}", response_model=ConfigOut)
def review_config(config_id: uuid.UUID, ctx: OrgContext = Depends(require_org_permission("agent.read")),
                  db: Session = Depends(get_db)):
    cfg, inst = approvals.get_config(db, ctx, config_id)
    return agents.config_out(db, inst, cfg)


@approvals_router.post("/configurations/{config_id}/decide", response_model=ApprovalOut)
def decide(config_id: uuid.UUID, data: s.DecideIn, ctx: OrgContext = Depends(require_org_permission("approval.decide")),
           db: Session = Depends(get_db)):
    approval = approvals.decide(db, ctx, config_id, data.decision, data.note, data.config_hash)
    return approvals.approval_out(db, approval)
