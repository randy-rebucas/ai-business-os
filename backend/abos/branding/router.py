from fastapi import APIRouter, Depends, File, Response, UploadFile
from sqlalchemy.orm import Session

from abos.branding import service
from abos.branding.logo import MAX_BYTES
from abos.branding.schemas import BrandingIn, BrandingOut
from abos.core.db import get_db
from abos.core.errors import AppError
from abos.identity.deps import OrgContext, per_user, require_org_permission

router = APIRouter(prefix="/api/v1/org/branding", tags=["branding"])
READ = require_org_permission("org.read")
MANAGE = require_org_permission("org.manage")


@router.get("", response_model=BrandingOut)
def get_branding(ctx: OrgContext = Depends(READ), db: Session = Depends(get_db)):
    return service.view(db, ctx.org_id)


@router.put("", response_model=BrandingOut)
def put_branding(data: BrandingIn, ctx: OrgContext = Depends(MANAGE), db: Session = Depends(get_db)):
    return service.update(db, ctx, data)


@router.post("/logo", response_model=BrandingOut, dependencies=[per_user("sensitive_user")])
def upload_logo(file: UploadFile = File(...), ctx: OrgContext = Depends(MANAGE), db: Session = Depends(get_db)):
    data = file.file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise AppError(422, "invalid_logo", "The logo must be 1 MB or smaller.")
    return service.upload_logo(db, ctx, data)


@router.delete("/logo", response_model=BrandingOut)
def remove_logo(ctx: OrgContext = Depends(MANAGE), db: Session = Depends(get_db)):
    return service.remove_logo(db, ctx)


@router.get("/logo")
def get_logo(ctx: OrgContext = Depends(READ), db: Session = Depends(get_db)):
    # Always a re-encoded PNG we produced; private caching is safe because the URL carries the file's version.
    return Response(service.logo(db, ctx.org_id), media_type="image/png",
                    headers={"Cache-Control": "private, max-age=86400", "Content-Disposition": "inline"})
