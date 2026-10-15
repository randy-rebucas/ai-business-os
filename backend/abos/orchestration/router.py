import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query
from pydantic import StringConstraints
from sqlalchemy import select
from sqlalchemy.orm import Session

from abos.agents import service as agents
from abos.agents.models import AgentDefinition
from abos.core.db import get_db
from abos.governance import actions
from abos.identity.deps import OrgContext, ai_work, require_org_permission
from abos.orchestration import schemas as s
from abos.orchestration import service
from abos.tools import registry

workflows_router = APIRouter(prefix="/api/v1/workflows", tags=["workflows"])
tools_router = APIRouter(prefix="/api/v1/tools", tags=["tools"])
actions_router = APIRouter(prefix="/api/v1/approvals/actions", tags=["approvals"])

READ = require_org_permission("task.read")
EVIDENCE = require_org_permission("records.read")  # run details and tool outputs contain business records
MANAGE = require_org_permission("task.manage")
AGENTS = require_org_permission("agent.read")
DECIDE = require_org_permission("approval.decide")
Status = Annotated[str, StringConstraints(max_length=30)]


def _run_out(run, name: str | None = None, key: str | None = None) -> s.RunOut:
    return s.RunOut.model_validate(run).model_copy(update={
        "agent_name": name, "definition_key": key, "summary": (run.output or {}).get("summary", ""),
        "validation_passed": (run.validation or {}).get("passed")})


# ---- workflow runs -----------------------------------------------------------------------------------------------

@workflows_router.get("", response_model=list[s.RunOut])
def list_runs(agent_id: uuid.UUID | None = None, status: Status | None = None, top_level: bool = False,
              limit: int = Query(50, ge=1, le=200), ctx: OrgContext = Depends(READ), db: Session = Depends(get_db)):
    return [_run_out(r, n, k) for r, n, k in service.list_runs(db, ctx, instance_id=agent_id, status=status,
                                                               top_level=top_level, limit=limit)]


@workflows_router.get("/tasks")
def runnable_tasks(ctx: OrgContext = Depends(READ), db: Session = Depends(get_db)):
    return service.runnable_tasks(db, ctx)


@workflows_router.post("", response_model=s.RunOut, status_code=202, dependencies=[ai_work()])
def start(data: s.RunIn, idempotency_key: Annotated[str | None, Header(max_length=100)] = None,
          ctx: OrgContext = Depends(MANAGE), db: Session = Depends(get_db)):
    inst = agents.get(db, ctx, data.agent_id)
    run = service.start(db, ctx, inst, task_key=data.task_key, request=data.request, idempotency_key=idempotency_key)
    db.refresh(run)
    return _run_out(run, inst.name, inst.definition_key)


@workflows_router.get("/{run_id}", response_model=s.RunDetailOut)
def run_detail(run_id: uuid.UUID, ctx: OrgContext = Depends(EVIDENCE), db: Session = Depends(get_db)):
    d = service.detail(db, ctx, service.get_run(db, ctx, run_id))
    run = d["run"]
    return s.RunDetailOut(**_run_out(run, d["agent_name"], d["definition_key"]).model_dump(), steps=run.steps,
                          output=run.output, validation=run.validation, error=run.error,
                          executions=[s.ExecutionOut.model_validate(x) for x in d["executions"]],
                          action_requests=d["action_requests"], children=d["children"], parent=d["parent"])


@workflows_router.post("/{run_id}/cancel", response_model=s.RunOut)
def cancel(run_id: uuid.UUID, ctx: OrgContext = Depends(MANAGE), db: Session = Depends(get_db)):
    run = service.cancel(db, ctx, service.get_run(db, ctx, run_id))
    return _run_out(run)


# ---- tool registry & ledger --------------------------------------------------------------------------------------

@tools_router.get("")
def tool_registry(agent_id: uuid.UUID | None = None, ctx: OrgContext = Depends(AGENTS),
                  db: Session = Depends(get_db)):
    """Every tool an agent of this workspace can name, with schemas, risk, approval, timeout and retry policy."""
    if agent_id:
        inst = agents.get(db, ctx, agent_id)
        specs = [db.get(AgentDefinition, inst.definition_id).spec]
    else:
        specs = [d.spec for d in db.scalars(select(AgentDefinition).where(AgentDefinition.is_current.is_(True)))]
    return {"version": registry.REGISTRY_VERSION, "tools": [t.describe() for t in registry.all_tools(specs)]}


@tools_router.get("/executions", response_model=list[s.ExecutionOut])
def tool_executions(run_id: uuid.UUID | None = None, agent_id: uuid.UUID | None = None,
                    tool: Annotated[str, StringConstraints(max_length=60)] | None = None,
                    limit: int = Query(100, ge=1, le=500), ctx: OrgContext = Depends(EVIDENCE),
                    db: Session = Depends(get_db)):
    return service.executions(db, ctx, run_id=run_id, instance_id=agent_id, tool=tool, limit=limit)


# ---- action approvals --------------------------------------------------------------------------------------------

@actions_router.get("", response_model=list[s.ActionRequestOut])
def action_requests(status: Status | None = "pending", ctx: OrgContext = Depends(EVIDENCE),
                    db: Session = Depends(get_db)):
    return [actions.out(db, a) for a in actions.listing(db, ctx, status or None)]


@actions_router.get("/{request_id}", response_model=s.ActionRequestOut)
def action_request(request_id: uuid.UUID, ctx: OrgContext = Depends(EVIDENCE), db: Session = Depends(get_db)):
    return actions.out(db, actions.get(db, ctx, request_id))


@actions_router.post("/{request_id}/decide", response_model=s.ActionRequestOut)
def decide(request_id: uuid.UUID, data: s.ActionDecisionIn, ctx: OrgContext = Depends(DECIDE),
           db: Session = Depends(get_db)):
    req = actions.decide(db, ctx, request_id, data.decision, data.note, data.params_hash)
    db.expire_all()
    return actions.out(db, db.get(type(req), req.id))

