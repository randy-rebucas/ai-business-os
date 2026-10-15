import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from abos.core.db import get_db
from abos.identity.deps import OrgContext, per_user, require_org_permission
from abos.privacy import service
from abos.privacy.schemas import DeletionIn, DeletionOut, ExportOut, RetentionIn, RetentionOut

router = APIRouter(prefix="/api/v1/org", tags=["data controls"])


@router.get("/retention", response_model=RetentionOut)
def get_retention(ctx: OrgContext = Depends(require_org_permission("org.read"))):
    return service.retention(ctx.organization)


@router.put("/retention", response_model=RetentionOut)
def put_retention(data: RetentionIn, ctx: OrgContext = Depends(require_org_permission("org.manage")),
                  db: Session = Depends(get_db)):
    return service.update_retention(db, ctx, data)


@router.get("/deletion", response_model=DeletionOut)
def get_deletion(ctx: OrgContext = Depends(require_org_permission("org.read"))):
    return service.deletion(ctx.organization)


@router.post("/deletion", response_model=DeletionOut, dependencies=[per_user("sensitive_user")])
def schedule_deletion(data: DeletionIn, ctx: OrgContext = Depends(require_org_permission("org.delete")),
                      db: Session = Depends(get_db)):
    return service.schedule_deletion(db, ctx, data.confirm_name, data.password)


@router.delete("/deletion", response_model=DeletionOut)
def cancel_deletion(ctx: OrgContext = Depends(require_org_permission("org.delete")), db: Session = Depends(get_db)):
    return service.cancel_deletion(db, ctx)


@router.get("/exports", response_model=list[ExportOut])
def list_exports(ctx: OrgContext = Depends(require_org_permission("org.export")), db: Session = Depends(get_db)):
    return service.list_exports(db, ctx.org_id)


@router.post("/exports", response_model=ExportOut, status_code=202, dependencies=[per_user("export_user")])
def request_export(ctx: OrgContext = Depends(require_org_permission("org.export")), db: Session = Depends(get_db)):
    return service.request_export(db, ctx)


@router.get("/exports/{export_id}/download")
def download_export(export_id: uuid.UUID, ctx: OrgContext = Depends(require_org_permission("org.export")),
                    db: Session = Depends(get_db)):
    data, name = service.export_file(db, ctx, export_id)
    return Response(data, media_type="application/zip",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})
