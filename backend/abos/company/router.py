import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from abos.company import schemas as s
from abos.company import service
from abos.core.db import get_db
from abos.identity.deps import OrgContext, current_auth, require_org_permission

router = APIRouter(prefix="/api/v1/company", tags=["company"])

READ = require_org_permission("company.read")
WRITE = require_org_permission("company.write")


@router.get("/profile", response_model=s.ProfileOut)
def get_profile(ctx: OrgContext = Depends(READ), db: Session = Depends(get_db)):
    return service.get_profile(db, ctx.org_id)


@router.patch("/profile", response_model=s.ProfileOut)
def update_profile(data: s.ProfileUpdateIn, ctx: OrgContext = Depends(WRITE), db: Session = Depends(get_db)):
    return service.update_profile(db, ctx, data)


@router.post("/onboarding/complete", response_model=s.ProfileOut)
def complete_onboarding(ctx: OrgContext = Depends(WRITE), db: Session = Depends(get_db)):
    """Mark the guided onboarding as finished. Missing sections stay listed by /completeness."""
    return service.complete_onboarding(db, ctx)


@router.get("/completeness", response_model=s.CompletenessOut)
def completeness(ctx: OrgContext = Depends(READ), db: Session = Depends(get_db)):
    return service.completeness(db, ctx.org_id)


@router.get("/timezones", response_model=list[str], dependencies=[Depends(current_auth)])
def timezones():
    return s.timezone_names()


def _register(c: service.Collection) -> None:
    """CRUD routes for one profile collection, typed with its own schemas (so OpenAPI stays precise)."""
    path = f"/{c.key}"

    def list_(ctx: OrgContext = Depends(READ), db: Session = Depends(get_db)):
        return service.list_items(db, ctx.org_id, c)

    def create(data: c.create, ctx: OrgContext = Depends(WRITE), db: Session = Depends(get_db)):  # type: ignore[name-defined]
        return service.create_item(db, ctx, c, data)

    def update(item_id: uuid.UUID, data: c.patch, ctx: OrgContext = Depends(WRITE),  # type: ignore[name-defined]
               db: Session = Depends(get_db)):
        return service.update_item(db, ctx, c, item_id, data)

    def delete(item_id: uuid.UUID, ctx: OrgContext = Depends(WRITE), db: Session = Depends(get_db)):
        service.delete_item(db, ctx, c, item_id)
        return Response(status_code=204)

    name = c.key.replace("-", "_")
    router.add_api_route(path, list_, methods=["GET"], response_model=list[c.out], name=f"list_{name}")
    router.add_api_route(path, create, methods=["POST"], response_model=c.out, status_code=201,
                         name=f"create_{name}")
    router.add_api_route(f"{path}/{{item_id}}", update, methods=["PATCH"], response_model=c.out,
                         name=f"update_{name}")
    router.add_api_route(f"{path}/{{item_id}}", delete, methods=["DELETE"], status_code=204, name=f"delete_{name}")


for _c in service.COLLECTIONS.values():
    _register(_c)
