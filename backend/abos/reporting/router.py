import uuid
from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy.orm import Session

from abos.agents import service as agents
from abos.core.db import get_db
from abos.identity.deps import OrgContext, ai_work, require_org_permission
from abos.reporting import dashboard, service

reports_router = APIRouter(prefix="/api/v1/reports", tags=["reports"])
dashboard_router = APIRouter(prefix="/api/v1/dashboard", tags=["reports"])

LIST = require_org_permission("report.read")
EVIDENCE = require_org_permission("records.read")  # report content quotes run summaries and records
GENERATE = require_org_permission("task.manage")
CONTROL = require_org_permission("task.read")
Short = Annotated[str, StringConstraints(max_length=120)]


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    instance_id: uuid.UUID
    agent_name: str | None = None
    report_date: date
    timezone: str
    period_start: datetime
    period_end: datetime
    final: bool
    version: int
    summary: str
    counts: dict[str, Any]
    generated_at: datetime


class ReportDetailOut(ReportOut):
    content: dict[str, Any]
    evidence: list[dict[str, Any]]


class GenerateIn(BaseModel):
    agent_id: uuid.UUID
    day: date | None = None


@reports_router.get("", response_model=list[ReportOut])
def reports(agent_id: uuid.UUID | None = None, date_from: date | None = None, date_to: date | None = None,
            limit: int = Query(100, ge=1, le=500), ctx: OrgContext = Depends(LIST), db: Session = Depends(get_db)):
    return [ReportOut.model_validate(r).model_copy(update={"agent_name": n})
            for r, n in service.listing(db, ctx, instance_id=agent_id, date_from=date_from, date_to=date_to,
                                        limit=limit)]


@reports_router.post("/generate", response_model=ReportOut, status_code=201, dependencies=[ai_work()])
def generate(data: GenerateIn, ctx: OrgContext = Depends(GENERATE), db: Session = Depends(get_db)):
    inst = agents.get(db, ctx, data.agent_id)
    return ReportOut.model_validate(service.generate_now(db, ctx, inst, data.day)).model_copy(
        update={"agent_name": inst.name})


@reports_router.get("/{report_id}", response_model=ReportDetailOut)
def report(report_id: uuid.UUID, ctx: OrgContext = Depends(EVIDENCE), db: Session = Depends(get_db)):
    r = service.get(db, ctx, report_id)
    inst = agents.get(db, ctx, r.instance_id)
    return ReportDetailOut(**ReportOut.model_validate(r).model_dump() | {"agent_name": inst.name}, content=r.content,
                           evidence=[{"section": e.section, "ref_type": e.ref_type, "ref_id": str(e.ref_id)}
                                     for e in service.evidence_of(db, r)])


@dashboard_router.get("")
def control_center(agent_id: uuid.UUID | None = None, department: Short | None = None, status: Short | None = None,
                   date_from: date | None = None, date_to: date | None = None, priority: Short | None = None,
                   ctx: OrgContext = Depends(CONTROL), db: Session = Depends(get_db)):
    return dashboard.control_center(db, ctx.org_id, agent_id=agent_id, department=department, status=status,
                                    date_from=date_from, date_to=date_to, priority=priority)
