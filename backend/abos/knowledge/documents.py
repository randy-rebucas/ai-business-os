"""Document lifecycle service: upload (validate + store), URL import, versions, retry/reprocess, review, archive.

Statuses: uploaded → queued → processing → awaiting_review → indexed;  failed (retryable);  superseded / archived.
Only `indexed` documents are retrievable, so nothing reaches an agent before a person has reviewed it (ADR-013).
"""

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from abos.audit import service as audit
from abos.core.config import get_settings
from abos.core.errors import AppError, conflict, not_found
from abos.identity.deps import OrgContext
from abos.jobs.service import enqueue
from abos.knowledge import fetch, parsing
from abos.knowledge.ingest import _store_version
from abos.knowledge.models import Document, DocumentChunk, DocumentVersion, JobRun


def allowed_levels(ctx: OrgContext) -> list[str]:
    """Access levels this member may see. Filtering happens in every query, retrieval included."""
    levels = ["general"]
    if ctx.can("knowledge.review"):
        levels.append("restricted")
    if ctx.can("knowledge.confidential"):
        levels.append("confidential")
    return levels


def _bad_file(exc: parsing.ParseError) -> AppError:
    return AppError(422, exc.code, str(exc))


def get(db: Session, ctx: OrgContext, doc_id: uuid.UUID) -> Document:
    doc = db.get(Document, doc_id)
    # Same 404 for "other org", "doesn't exist" and "above your access level" — no probing.
    if doc is None or doc.organization_id != ctx.org_id or doc.access_level not in allowed_levels(ctx):
        raise not_found("Document")
    return doc


def list_documents(db: Session, ctx: OrgContext, status: str | None = None, doc_type: str | None = None,
                   q: str | None = None) -> list[Document]:
    stmt = (select(Document).where(Document.organization_id == ctx.org_id,
                                   Document.access_level.in_(allowed_levels(ctx)))
            .order_by(Document.created_at.desc()).limit(500))
    if status:
        stmt = stmt.where(Document.status == status)
    if doc_type:
        stmt = stmt.where(Document.doc_type == doc_type)
    if q:
        stmt = stmt.where(Document.title.ilike(f"%{q}%"))
    return list(db.scalars(stmt))


def _check_supersedes(db: Session, ctx: OrgContext, target: uuid.UUID | None, self_id: uuid.UUID | None) -> None:
    if target is None:
        return
    if target == self_id:
        raise AppError(422, "validation_error", "A document can't supersede itself")
    get(db, ctx, target)


def upload(db: Session, ctx: OrgContext, *, filename: str, data: bytes, title: str | None, access_level: str,
           effective_date: date | None, supersedes_id: uuid.UUID | None) -> Document:
    s = get_settings()
    if len(data) > s.upload_max_bytes:
        raise AppError(413, "too_large", f"Files are limited to {s.upload_max_bytes // (1024 * 1024)} MB")
    if access_level not in allowed_levels(ctx):
        raise AppError(403, "forbidden", "You can't classify documents above your own access level")
    try:
        fmt = parsing.sniff(data, filename)                                       # step 1
    except parsing.ParseError as exc:
        raise _bad_file(exc) from exc
    _check_supersedes(db, ctx, supersedes_id, None)
    safe_name = filename.replace("\\", "/").rsplit("/", 1)[-1][:300]
    doc = Document(organization_id=ctx.org_id, title=(title or safe_name.rsplit(".", 1)[0])[:300], source_type="upload",
                   original_filename=safe_name, mime_type=parsing.MIME[fmt], status="uploaded",
                   access_level=access_level, effective_date=effective_date, supersedes_document_id=supersedes_id,
                   uploaded_by_id=ctx.user.id, warnings=[])
    db.add(doc)
    db.flush()
    version = _store_version(db, doc, data, fmt, parsing.MIME[fmt], created_by=ctx.user.id)  # step 2
    doc.status = "queued"
    enqueue(db, ctx.org_id, "ingest_document", doc.id)
    audit.record(db, "knowledge.document_uploaded", actor_id=ctx.user.id, org_id=ctx.org_id, target_type="document",
                 target_id=doc.id, data={"filename": safe_name, "bytes": len(data), "sha256": version.sha256,
                                         "access_level": access_level}, ip=ctx.meta.ip)
    db.commit()
    db.refresh(doc)
    return doc


def add_url(db: Session, ctx: OrgContext, url: str, title: str | None, access_level: str) -> Document:
    if access_level not in allowed_levels(ctx):
        raise AppError(403, "forbidden", "You can't classify documents above your own access level")
    try:
        fetch.validate_url(url)  # syntax/scheme/port now; DNS + IP checks happen in the worker on every hop
    except parsing.ParseError as exc:
        raise _bad_file(exc) from exc
    doc = Document(organization_id=ctx.org_id, title=(title or url)[:300], source_type="url", source_url=url,
                   mime_type=None, status="queued", access_level=access_level, uploaded_by_id=ctx.user.id,
                   warnings=[])
    db.add(doc)
    db.flush()
    enqueue(db, ctx.org_id, "ingest_document", doc.id)
    audit.record(db, "knowledge.url_added", actor_id=ctx.user.id, org_id=ctx.org_id, target_type="document",
                 target_id=doc.id, data={"url": url}, ip=ctx.meta.ip)
    db.commit()
    db.refresh(doc)
    return doc


def _requeue(db: Session, ctx: OrgContext, doc: Document, action: str, **data) -> Document:
    doc.status, doc.error_code, doc.error_message = "queued", None, None
    doc.reviewed_by_id = doc.reviewed_at = doc.indexed_at = None
    enqueue(db, ctx.org_id, "ingest_document", doc.id)
    audit.record(db, f"knowledge.document_{action}", actor_id=ctx.user.id, org_id=ctx.org_id,
                 target_type="document", target_id=doc.id, data=data, ip=ctx.meta.ip)
    db.commit()
    db.refresh(doc)
    return doc


def add_version(db: Session, ctx: OrgContext, doc: Document, filename: str, data: bytes) -> Document:
    if doc.status in ("queued", "processing"):
        raise conflict("This document is still being processed")
    if doc.status == "archived":
        raise conflict("Restore the document before adding a version")
    if len(data) > get_settings().upload_max_bytes:
        raise AppError(413, "too_large", "File is too large")
    try:
        fmt = parsing.sniff(data, filename)
    except parsing.ParseError as exc:
        raise _bad_file(exc) from exc
    version = _store_version(db, doc, data, fmt, parsing.MIME[fmt], created_by=ctx.user.id)
    doc.mime_type, doc.original_filename = parsing.MIME[fmt], filename.rsplit("/", 1)[-1][:300]
    if doc.status == "superseded":
        doc.supersedes_document_id = None
    return _requeue(db, ctx, doc, "version_added", version=version.version_no, sha256=version.sha256)


def retry(db: Session, ctx: OrgContext, doc: Document) -> Document:
    if doc.status != "failed":
        raise conflict("Only failed documents can be retried")
    return _requeue(db, ctx, doc, "retried")


def reprocess(db: Session, ctx: OrgContext, doc: Document) -> Document:
    """Re-index the current version (e.g. after changing the embedding model). Needs review again."""
    if doc.status not in ("indexed", "awaiting_review", "failed"):
        raise conflict(f"A document that is {doc.status.replace('_', ' ')} can't be reprocessed")
    return _requeue(db, ctx, doc, "reprocessed")


def update(db: Session, ctx: OrgContext, doc: Document, patch: dict) -> Document:
    if "access_level" in patch and patch["access_level"] not in allowed_levels(ctx):
        raise AppError(403, "forbidden", "You can't classify documents above your own access level")
    if "supersedes_document_id" in patch:
        _check_supersedes(db, ctx, patch["supersedes_document_id"], doc.id)
    if patch.get("doc_type"):
        doc.doc_type_source = "reviewer"
    changed = {k: v for k, v in patch.items() if getattr(doc, k) != v}
    for k, v in changed.items():
        setattr(doc, k, v)
    if changed:
        audit.record(db, "knowledge.document_updated", actor_id=ctx.user.id, org_id=ctx.org_id,
                     target_type="document", target_id=doc.id, data={"fields": sorted(changed)}, ip=ctx.meta.ip)
    db.commit()
    db.refresh(doc)
    return doc


def review(db: Session, ctx: OrgContext, doc: Document, decision: str, note: str | None, meta: dict) -> Document:
    """The CEO/manager confirms the extracted content represents the business (SPEC step 1 review screen)."""
    if doc.status != "awaiting_review":
        raise conflict("Only documents awaiting review can be approved or rejected")
    if meta:
        update(db, ctx, doc, meta)
    now = datetime.now(UTC)
    doc.reviewed_by_id, doc.reviewed_at, doc.review_note = ctx.user.id, now, note
    superseded = None
    if decision == "approve":
        doc.status, doc.indexed_at = "indexed", now
        if doc.supersedes_document_id:
            old = db.get(Document, doc.supersedes_document_id)
            if old is not None and old.organization_id == ctx.org_id and old.status != "archived":
                old.status, superseded = "superseded", old.id
    else:
        doc.status = "archived"
    audit.record(db, f"knowledge.document_{'approved' if decision == 'approve' else 'rejected'}",
                 actor_id=ctx.user.id, org_id=ctx.org_id, target_type="document", target_id=doc.id,
                 data={"note": note, "superseded": str(superseded) if superseded else None,
                       "version_id": str(doc.current_version_id)}, ip=ctx.meta.ip)
    db.commit()
    db.refresh(doc)
    return doc


def archive(db: Session, ctx: OrgContext, doc: Document) -> Document:
    if doc.status in ("queued", "processing"):
        raise conflict("Wait for processing to finish before archiving")
    if doc.status != "archived":
        previous, doc.status = doc.status, "archived"
        audit.record(db, "knowledge.document_archived", actor_id=ctx.user.id, org_id=ctx.org_id,
                     target_type="document", target_id=doc.id, data={"from": previous}, ip=ctx.meta.ip)
        db.commit()
        db.refresh(doc)
    return doc


def restore(db: Session, ctx: OrgContext, doc: Document) -> Document:
    if doc.status != "archived":
        raise conflict("Only archived documents can be restored")
    # Back through review: archived content may be outdated.
    doc.status = "awaiting_review" if doc.chunk_count else "failed"
    audit.record(db, "knowledge.document_restored", actor_id=ctx.user.id, org_id=ctx.org_id,
                 target_type="document", target_id=doc.id, ip=ctx.meta.ip)
    db.commit()
    db.refresh(doc)
    return doc


def versions(db: Session, doc: Document) -> list[DocumentVersion]:
    return list(db.scalars(select(DocumentVersion).where(DocumentVersion.document_id == doc.id)
                           .order_by(DocumentVersion.version_no.desc())))


def latest_job(db: Session, doc: Document) -> JobRun | None:
    return db.scalars(select(JobRun).where(JobRun.target_id == doc.id).order_by(JobRun.created_at.desc())).first()


def chunks(db: Session, doc: Document, limit: int = 200) -> list[DocumentChunk]:
    return list(db.scalars(select(DocumentChunk).where(DocumentChunk.document_id == doc.id)
                           .order_by(DocumentChunk.chunk_index).limit(limit)))


def superseded_by(db: Session, doc: Document) -> list[Document]:
    return list(db.scalars(select(Document).where(Document.supersedes_document_id == doc.id,
                                                  Document.organization_id == doc.organization_id)))


def version_for_download(db: Session, doc: Document, version_id: uuid.UUID | None) -> DocumentVersion:
    vid = version_id or doc.current_version_id
    version = db.get(DocumentVersion, vid) if vid else None
    if version is None or version.document_id != doc.id:
        raise not_found("File")
    return version
