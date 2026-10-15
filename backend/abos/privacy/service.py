"""Workspace data controls: retention settings, export, scheduled deletion (docs/OPERATIONS.md, ADR-033).

- Retention: per-workspace windows for notifications, Ask history and daily reports; housekeeping purges past them.
  Evidence, ledgers, audit and business records are kept while the workspace exists (`KEPT`).
- Export: a job writes one JSON file per tenant table plus the original document files into a zip in private
  storage; downloadable by the requester's workspace owners until it expires.
- Deletion: an owner confirms the workspace name and their password; deletion is scheduled after a grace period
  (owners can cancel) and then performed by housekeeping on the owner path (`housekeeping.delete_organization`).
"""

import io
import json
import uuid
import zipfile
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from abos.audit import service as audit
from abos.core.config import get_settings
from abos.core.db import Base
from abos.core.errors import AppError, conflict, not_found, report_exception
from abos.core.security import verify_password
from abos.identity import mailer
from abos.identity.deps import OrgContext
from abos.identity.models import Organization, OrganizationMembership, User
from abos.jobs import service as jobs
from abos.knowledge.models import JobRun
from abos.privacy.models import OrgExport
from abos.privacy.schemas import DeletionOut, RetentionIn, RetentionOut
from abos.storage import export_key, get_storage

EXPORT_JOB = "org_export"
EXPORT_FORMAT = "abos-export/1"
KEPT = [
    "Audit log — append-only security record.",
    "Agent run evidence (tool executions, reconciliations) and approvals — they prove what agents did.",
    "Business records (invoices, payments, expenses) — accounting records.",
    "Model usage — needed for budgets and cost history.",
    "Documents — until you archive or delete the workspace.",
]
# Never exported: derived search data (rebuilt by re-indexing) — large and meaningless outside the platform.
_SKIP_COLUMNS = {"embedding", "tsv"}


def _now() -> datetime:
    return datetime.now(UTC)


# ---- retention ---------------------------------------------------------------------------------

def retention(org: Organization) -> RetentionOut:
    return RetentionOut(notifications_days=org.retention_notifications_days,
                        ask_history_days=org.retention_ask_history_days,
                        reports_days=org.retention_reports_days, kept=KEPT)


def update_retention(db: Session, ctx: OrgContext, data: RetentionIn) -> RetentionOut:
    org = ctx.organization
    before = retention(org).model_dump(exclude={"kept"})
    org.retention_notifications_days = data.notifications_days
    org.retention_ask_history_days = data.ask_history_days
    org.retention_reports_days = data.reports_days
    audit.record(db, "org.retention_updated", actor_id=ctx.user.id, org_id=ctx.org_id, target_type="organization",
                 target_id=ctx.org_id, data={"from": before, "to": data.model_dump()}, ip=ctx.meta.ip)
    db.commit()
    return retention(org)


# ---- deletion ----------------------------------------------------------------------------------

def deletion(org: Organization) -> DeletionOut:
    return DeletionOut(scheduled_for=org.deletion_scheduled_at, requested_by_id=org.deletion_requested_by_id,
                       grace_hours=get_settings().org_deletion_grace_hours)


def _owner_emails(db: Session, org_id: uuid.UUID) -> list[str]:
    return list(db.scalars(select(User.email).join(OrganizationMembership, OrganizationMembership.user_id == User.id)
                           .where(OrganizationMembership.organization_id == org_id,
                                  OrganizationMembership.role == "owner")))


def schedule_deletion(db: Session, ctx: OrgContext, confirm_name: str, password: str) -> DeletionOut:
    org = ctx.organization
    if confirm_name.strip() != org.name:
        raise AppError(400, "confirmation_mismatch", "Type the workspace name exactly to confirm")
    if not verify_password(ctx.user.password_hash, password):
        raise AppError(400, "invalid_credentials", "Password is incorrect")
    if org.deletion_scheduled_at is not None:
        raise conflict("Deletion is already scheduled")
    org.deletion_scheduled_at = _now() + timedelta(hours=get_settings().org_deletion_grace_hours)
    org.deletion_requested_by_id = ctx.user.id
    audit.record(db, "org.deletion_scheduled", actor_id=ctx.user.id, org_id=ctx.org_id, target_type="organization",
                 target_id=ctx.org_id, data={"scheduled_for": org.deletion_scheduled_at.isoformat()}, ip=ctx.meta.ip)
    when = org.deletion_scheduled_at.strftime("%Y-%m-%d %H:%M UTC")
    for email in _owner_emails(db, ctx.org_id):
        mailer.send(db, email, f"Workspace {org.name} is scheduled for deletion",
                    f"{ctx.user.full_name} scheduled the workspace \"{org.name}\" for permanent deletion at {when}.\n\n"
                    "All of its documents, agents, runs, reports and records will be deleted and cannot be "
                    "recovered. Any owner can cancel before then in Settings → Data & privacy.\n")
    db.commit()
    return deletion(org)


def cancel_deletion(db: Session, ctx: OrgContext) -> DeletionOut:
    org = ctx.organization
    if org.deletion_scheduled_at is None:
        raise conflict("No deletion is scheduled")
    previous = org.deletion_scheduled_at
    org.deletion_scheduled_at = org.deletion_requested_by_id = None
    audit.record(db, "org.deletion_cancelled", actor_id=ctx.user.id, org_id=ctx.org_id, target_type="organization",
                 target_id=ctx.org_id, data={"was_scheduled_for": previous.isoformat()}, ip=ctx.meta.ip)
    db.commit()
    return deletion(org)


# ---- export ------------------------------------------------------------------------------------

def request_export(db: Session, ctx: OrgContext) -> OrgExport:
    busy = db.scalar(select(OrgExport.id).where(OrgExport.organization_id == ctx.org_id,
                                                OrgExport.status.in_(("queued", "building"))))
    if busy:
        raise conflict("An export is already being prepared")
    export = OrgExport(id=uuid.uuid4(), organization_id=ctx.org_id, requested_by_id=ctx.user.id, status="queued")
    db.add(export)
    audit.record(db, "org.export_requested", actor_id=ctx.user.id, org_id=ctx.org_id, target_type="org_export",
                 target_id=export.id, ip=ctx.meta.ip)
    jobs.enqueue(db, ctx.org_id, EXPORT_JOB, export.id)
    db.commit()
    db.refresh(export)
    return export


def list_exports(db: Session, org_id: uuid.UUID) -> list[OrgExport]:
    return list(db.scalars(select(OrgExport).where(OrgExport.organization_id == org_id)
                           .order_by(OrgExport.created_at.desc()).limit(20)))


def export_file(db: Session, ctx: OrgContext, export_id: uuid.UUID) -> tuple[bytes, str]:
    export = db.get(OrgExport, export_id)
    if export is None or export.organization_id != ctx.org_id:
        raise not_found("Export")
    if export.status != "ready" or export.storage_key is None or (export.expires_at and export.expires_at <= _now()):
        raise conflict("This export is not available for download")
    audit.record(db, "org.export_downloaded", actor_id=ctx.user.id, org_id=ctx.org_id, target_type="org_export",
                 target_id=export.id, ip=ctx.meta.ip)
    db.commit()
    stamp = export.created_at.strftime("%Y%m%d-%H%M")
    return get_storage().get(export.storage_key), f"{ctx.organization.slug}-export-{stamp}.zip"


def _json_value(value: Any) -> Any:
    if isinstance(value, uuid.UUID | datetime | date | Decimal):
        return str(value) if not isinstance(value, datetime | date) else value.isoformat()
    return value


def tenant_tables() -> list:
    return [t for t in Base.metadata.sorted_tables if "organization_id" in t.c]


def build_archive(db: Session, org_id: uuid.UUID) -> tuple[bytes, dict[str, Any]]:
    """Every tenant table (rows read through the RLS-bound session *and* filtered by org), the workspace, its
    members (no credentials) and the original document files."""
    org = db.get(Organization, org_id)
    assert org is not None
    buf = io.BytesIO()
    counts: dict[str, int] = {}
    files = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        def put(name: str, rows: list[dict[str, Any]]) -> None:
            z.writestr(name, json.dumps(rows, default=_json_value, ensure_ascii=False, indent=1))

        put("workspace.json", [{"id": org.id, "name": org.name, "slug": org.slug, "created_at": org.created_at,
                                "retention": retention(org).model_dump(exclude={"kept"})}])
        members = db.execute(select(User.id, User.email, User.full_name, OrganizationMembership.role,
                                    OrganizationMembership.job_title)
                             .join(OrganizationMembership, OrganizationMembership.user_id == User.id)
                             .where(OrganizationMembership.organization_id == org_id)).mappings().all()
        put("members.json", [dict(m) for m in members])
        for table in tenant_tables():
            cols = [c for c in table.c if c.name not in _SKIP_COLUMNS]
            rows = [dict(r) for r in db.execute(select(*cols).where(table.c.organization_id == org_id)).mappings()]
            counts[table.name] = len(rows)
            put(f"tables/{table.name}.json", rows)
        from abos.knowledge.models import DocumentVersion  # noqa: PLC0415

        storage = get_storage()
        for v in db.scalars(select(DocumentVersion).where(DocumentVersion.organization_id == org_id)):
            try:
                z.writestr(f"files/{v.document_id}/v{v.version_no}.{v.detected_format}", storage.get(v.storage_key))
                files += 1
            except (OSError, ValueError, KeyError):
                counts.setdefault("_missing_files", 0)
                counts["_missing_files"] += 1
        from abos.branding.models import WorkspaceBranding  # noqa: PLC0415

        brand = db.scalar(select(WorkspaceBranding).where(WorkspaceBranding.organization_id == org_id))
        if brand is not None and brand.logo_key:
            try:
                z.writestr("files/branding/logo.png", storage.get(brand.logo_key))
                files += 1
            except (OSError, ValueError, KeyError):
                counts["_missing_files"] = counts.get("_missing_files", 0) + 1
        manifest = {"format": EXPORT_FORMAT, "organization_id": str(org_id), "generated_at": _now().isoformat(),
                    "tables": counts, "files": files,
                    "notes": "Search embeddings are not exported; re-indexing the documents rebuilds them."}
        z.writestr("manifest.json", json.dumps(manifest, indent=1))
    return buf.getvalue(), manifest


@jobs.handler(EXPORT_JOB)
def run_export(db: Session, job: JobRun) -> None:
    export = db.get(OrgExport, job.target_id)
    if export is None or export.status not in ("queued", "building"):
        return
    export.status = "building"
    db.commit()
    try:
        data, manifest = build_archive(db, export.organization_id)
        key = export_key(export.organization_id, export.id)
        get_storage().put(key, data, "application/zip")
    except Exception as exc:  # noqa: BLE001 — recorded on the export, reported, not retried
        db.rollback()
        report_exception(exc, {"export_id": str(job.target_id)}, where="job")
        export = db.get(OrgExport, job.target_id)
        export.status, export.error = "failed", f"{type(exc).__name__}"[:300]
        db.commit()
        raise jobs.JobFailed("export failed") from exc
    export.status, export.storage_key, export.size_bytes = "ready", key, len(data)
    export.manifest, export.expires_at = manifest, _now() + timedelta(hours=get_settings().export_ttl_hours)
    db.commit()
