import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Query
from pydantic import StringConstraints
from sqlalchemy.orm import Session

from abos.agents import lifecycle, policy, recommend, service
from abos.agents import schemas as s
from abos.core.db import get_db
from abos.core.errors import AppError
from abos.identity.deps import OrgContext, ai_work, require_org_permission
from abos.llm import gateway

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])

READ = require_org_permission("agent.read")
CONFIGURE = require_org_permission("agent.configure")
HIRE = require_org_permission("agent.hire")


@router.get("/policy")
def policy_vocabulary(_: OrgContext = Depends(READ)):
    """Scopes, risks, events, modes — so the UI never hard-codes governance vocabulary."""
    return {
        "scopes": [{"key": k, "label": label, "risk": risk, "max_mode": ceiling, "default_mode": policy.DEFAULT_MODE[k]}
                   for k, (label, risk, ceiling) in policy.SCOPES.items()],
        "events": [{"key": k, "label": v} for k, v in policy.EVENTS.items()],
        "operating_modes": [{"key": k, "label": v} for k, v in policy.OPERATING_MODES.items()],
        "automation_levels": [{"key": k, "label": v} for k, v in policy.AUTOMATION_LEVELS.items()],
        "lifecycle": [{"key": k, "label": v} for k, v in lifecycle.LABELS.items()],
    }


@router.get("/catalog", response_model=list[s.DefinitionOut])
def catalog(ctx: OrgContext = Depends(READ), db: Session = Depends(get_db)):
    return service.catalog(db, ctx.org_id)


@router.get("/catalog/{key}", response_model=s.DefinitionOut)
def catalog_entry(key: Annotated[str, StringConstraints(max_length=40)], ctx: OrgContext = Depends(READ),
                  db: Session = Depends(get_db)):
    return next((d for d in service.catalog(db, ctx.org_id) if d.key == key), None) or \
        service.definition_out(service.current_definition(db, key))


@router.get("/recommendation", response_model=s.RecommendationOut)
def recommendation(ctx: OrgContext = Depends(READ), db: Session = Depends(get_db)):
    return recommend.recommend(db, ctx.org_id)


@router.get("", response_model=list[s.InstanceListItem])
def list_agents(include_retired: bool = Query(False), ctx: OrgContext = Depends(READ), db: Session = Depends(get_db)):
    return service.list_instances(db, ctx, include_retired)


@router.post("", response_model=list[s.InstanceOut], status_code=201)
def hire(data: s.HireIn, ctx: OrgContext = Depends(HIRE), db: Session = Depends(get_db)):
    return service.hire(db, ctx, data.definition_keys, data.source)


@router.get("/{instance_id}", response_model=s.InstanceDetailOut)
def get_agent(instance_id: uuid.UUID, ctx: OrgContext = Depends(READ), db: Session = Depends(get_db)):
    return service.detail(db, ctx, service.get(db, ctx, instance_id))


@router.post("/{instance_id}/config/generate", response_model=s.ConfigOut, dependencies=[ai_work()])
def generate(instance_id: uuid.UUID, ctx: OrgContext = Depends(CONFIGURE), db: Session = Depends(get_db)):
    inst = service.get(db, ctx, instance_id)
    try:
        cfg = service.generate(db, ctx, inst)
    except gateway.LLMError as exc:
        raise AppError(502 if exc.code != "not_configured" else 503, f"ai_{exc.code}", str(exc)) from exc
    return service.config_out(db, inst, cfg)


@router.put("/{instance_id}/config/draft", response_model=s.ConfigOut)
def save_draft(instance_id: uuid.UUID, data: s.DraftIn, ctx: OrgContext = Depends(CONFIGURE),
               db: Session = Depends(get_db)):
    inst = service.get(db, ctx, instance_id)
    return service.config_out(db, inst, service.save_draft(db, ctx, inst, data))


@router.post("/{instance_id}/config/submit", response_model=s.ConfigOut)
def submit(instance_id: uuid.UUID, ctx: OrgContext = Depends(CONFIGURE), db: Session = Depends(get_db)):
    inst = service.get(db, ctx, instance_id)
    return service.config_out(db, inst, service.submit(db, ctx, inst))


@router.get("/{instance_id}/config/versions", response_model=list[s.ConfigSummaryOut])
def versions(instance_id: uuid.UUID, ctx: OrgContext = Depends(READ), db: Session = Depends(get_db)):
    return service.versions(db, service.get(db, ctx, instance_id))


@router.get("/{instance_id}/config/versions/{version}", response_model=s.ConfigOut)
def version(instance_id: uuid.UUID, version: int, ctx: OrgContext = Depends(READ), db: Session = Depends(get_db)):
    inst = service.get(db, ctx, instance_id)
    return service.config_out(db, inst, service.get_version(db, inst, version))


@router.get("/{instance_id}/schedule", response_model=s.SchedulePreviewOut)
def schedule_preview(instance_id: uuid.UUID, ctx: OrgContext = Depends(READ), db: Session = Depends(get_db)):
    inst = service.get(db, ctx, instance_id)
    if inst.current_config_id is None:
        raise AppError(409, "no_configuration", "Generate a configuration first")
    return service.schedule_preview(db, inst, service.current_config(db, inst))


@router.post("/{instance_id}/retire", response_model=s.InstanceOut)
def retire(instance_id: uuid.UUID,
           reason: Annotated[str | None, Body(embed=True, max_length=300)] = None,
           ctx: OrgContext = Depends(HIRE), db: Session = Depends(get_db)):
    return service.retire(db, ctx, service.get(db, ctx, instance_id), reason)
