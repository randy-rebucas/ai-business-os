import uuid

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from abos.agents import service as agents
from abos.agents.models import AgentInstance
from abos.agents.schemas import ConfigOut, InstanceOut
from abos.core.db import get_db
from abos.identity.deps import OrgContext, ai_work, require_org_permission
from abos.knowledge.models import JobRun
from abos.simulation import schemas as s
from abos.simulation import service

simulations_router = APIRouter(prefix="/api/v1/simulations", tags=["simulation"])
agent_router = APIRouter(prefix="/api/v1/agents", tags=["simulation"])

READ = require_org_permission("agent.read")
RUN = require_org_permission("simulation.run")
CONFIGURE = require_org_permission("agent.configure")
ACTIVATE = require_org_permission("agent.activate")


def _run_out(db: Session, run) -> s.RunOut:
    inst = db.get(AgentInstance, run.instance_id)
    return s.RunOut.model_validate(run).model_copy(update={"agent_name": inst.name if inst else None})


# ---- scenarios & runs --------------------------------------------------------------------------------------------

@simulations_router.get("/scenarios", response_model=list[s.ScenarioOut])
def scenarios(agent_key: str = Query(..., max_length=40), ctx: OrgContext = Depends(READ),
              db: Session = Depends(get_db)):
    agents.current_definition(db, agent_key)  # 404 for unknown keys
    return service.list_scenarios(db, ctx.org_id, agent_key)


@simulations_router.post("/scenarios", response_model=s.ScenarioOut, status_code=201)
def create_scenario(data: s.ScenarioIn, ctx: OrgContext = Depends(RUN), db: Session = Depends(get_db)):
    service.ensure_library(db, ctx.org_id, data.agent_key)
    return service.create_custom(db, ctx, data)


@simulations_router.delete("/scenarios/{scenario_id}", status_code=204)
def delete_scenario(scenario_id: uuid.UUID, ctx: OrgContext = Depends(RUN), db: Session = Depends(get_db)):
    service.delete_custom(db, ctx, scenario_id)
    return Response(status_code=204)


@simulations_router.get("/runs", response_model=list[s.RunOut])
def all_runs(limit: int = Query(50, ge=1, le=200), ctx: OrgContext = Depends(READ), db: Session = Depends(get_db)):
    return [_run_out(db, r) for r in service.runs_for(db, ctx.org_id, limit=limit)]


@simulations_router.get("/runs/{run_id}", response_model=s.RunDetailOut)
def run_detail(run_id: uuid.UUID, ctx: OrgContext = Depends(READ), db: Session = Depends(get_db)):
    run = service.get_run(db, ctx, run_id)
    job = db.scalar(select(JobRun).where(JobRun.kind == "simulation_run", JobRun.target_id == run.id)
                    .order_by(JobRun.created_at.desc()))
    return s.RunDetailOut(**_run_out(db, run).model_dump(),
                          results=[s.ResultOut.model_validate(r) for r in service.results(db, run)],
                          progress=job.steps if job else [])


@simulations_router.post("/results/{result_id}/suggestions/{index}/apply", response_model=ConfigOut)
def apply_suggestion(result_id: uuid.UUID, index: int, ctx: OrgContext = Depends(CONFIGURE),
                     db: Session = Depends(get_db)):
    cfg = service.apply_suggestion(db, ctx, result_id, index)
    return agents.config_out(db, db.get(AgentInstance, cfg.instance_id), cfg)


# ---- per agent: runs, readiness, deployment ----------------------------------------------------------------------

@agent_router.post("/{instance_id}/simulations", response_model=s.RunOut, status_code=202, dependencies=[ai_work()])
def start_run(instance_id: uuid.UUID, ctx: OrgContext = Depends(RUN), db: Session = Depends(get_db)):
    run = service.start_run(db, ctx, agents.get(db, ctx, instance_id))
    db.refresh(run)
    return _run_out(db, run)


@agent_router.get("/{instance_id}/simulations", response_model=list[s.RunOut])
def agent_runs(instance_id: uuid.UUID, ctx: OrgContext = Depends(READ), db: Session = Depends(get_db)):
    inst = agents.get(db, ctx, instance_id)
    return [_run_out(db, r) for r in service.runs_for(db, ctx.org_id, inst.id)]


@agent_router.get("/{instance_id}/readiness")
def readiness(instance_id: uuid.UUID, ctx: OrgContext = Depends(READ), db: Session = Depends(get_db)):
    return service.readiness(db, agents.get(db, ctx, instance_id))


@agent_router.post("/{instance_id}/activate", response_model=InstanceOut)
def activate(instance_id: uuid.UUID, data: s.ReviewedIn, ctx: OrgContext = Depends(ACTIVATE),
             db: Session = Depends(get_db)):
    return service.activate(db, ctx, agents.get(db, ctx, instance_id), data.config_hash, data.note)


@agent_router.post("/{instance_id}/widen", response_model=InstanceOut)
def widen(instance_id: uuid.UUID, data: s.ReviewedIn, ctx: OrgContext = Depends(ACTIVATE),
          db: Session = Depends(get_db)):
    return service.widen(db, ctx, agents.get(db, ctx, instance_id), data.config_hash, data.note)


@agent_router.post("/{instance_id}/pause", response_model=InstanceOut)
def pause(instance_id: uuid.UUID, data: s.PauseIn, ctx: OrgContext = Depends(ACTIVATE),
          db: Session = Depends(get_db)):
    return service.pause(db, ctx, agents.get(db, ctx, instance_id), data.reason)


@agent_router.post("/{instance_id}/resume", response_model=InstanceOut)
def resume(instance_id: uuid.UUID, data: s.ReviewedIn, ctx: OrgContext = Depends(ACTIVATE),
           db: Session = Depends(get_db)):
    return service.resume(db, ctx, agents.get(db, ctx, instance_id), data.config_hash)


@agent_router.post("/{instance_id}/config/rollback", response_model=ConfigOut)
def rollback(instance_id: uuid.UUID, data: s.RollbackIn, ctx: OrgContext = Depends(CONFIGURE),
             db: Session = Depends(get_db)):
    inst = agents.get(db, ctx, instance_id)
    return agents.config_out(db, inst, service.rollback(db, ctx, inst, data.version))
