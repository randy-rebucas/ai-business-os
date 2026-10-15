import uuid
from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from abos.core.config import get_settings
from abos.core.db import get_db
from abos.core.errors import AppError, not_found
from abos.identity.deps import OrgContext, ai_work, per_user, require_org_permission
from abos.knowledge import answer as answering
from abos.knowledge import documents as docs
from abos.knowledge import evals, interview, retrieval
from abos.knowledge import schemas as s
from abos.knowledge.models import KnowledgeQuery, RagEvalCase, RagEvalResult, RagEvalRun
from abos.llm import gateway
from abos.storage import get_storage

documents_router = APIRouter(prefix="/api/v1/documents", tags=["documents"])
knowledge_router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])
interview_router = APIRouter(prefix="/api/v1/interview", tags=["interview"])

READ = require_org_permission("knowledge.read")
UPLOAD = require_org_permission("knowledge.upload")
REVIEW = require_org_permission("knowledge.review")


async def _read_capped(file: UploadFile) -> bytes:
    limit = get_settings().upload_max_bytes
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise AppError(413, "too_large", f"Files are limited to {limit // (1024 * 1024)} MB")
    return data


def _detail(db: Session, doc) -> s.DocumentDetailOut:
    job = docs.latest_job(db, doc)
    return s.DocumentDetailOut(
        **s.DocumentOut.model_validate(doc).model_dump(),
        versions=[s.VersionOut.model_validate(v) for v in docs.versions(db, doc)],
        latest_job=s.JobOut.model_validate(job) if job else None,
        superseded_by=[{"id": str(d.id), "title": d.title, "status": d.status} for d in docs.superseded_by(db, doc)])


# ---- documents -------------------------------------------------------------------------------------------------

@documents_router.get("", response_model=list[s.DocumentOut])
def list_documents(status: str | None = Query(None, max_length=20), doc_type: str | None = Query(None, max_length=30),
                   q: str | None = Query(None, max_length=200), ctx: OrgContext = Depends(READ),
                   db: Session = Depends(get_db)):
    return docs.list_documents(db, ctx, status, doc_type, q)


@documents_router.post("", response_model=s.DocumentOut, status_code=201, dependencies=[ai_work()])
async def upload(file: UploadFile = File(...), title: str | None = Form(None, max_length=300),
                 access_level: s.AccessLevel = Form("general"), effective_date: date | None = Form(None),
                 supersedes_document_id: uuid.UUID | None = Form(None), ctx: OrgContext = Depends(UPLOAD),
                 db: Session = Depends(get_db)):
    data = await _read_capped(file)
    return docs.upload(db, ctx, filename=file.filename or "upload", data=data, title=(title or "").strip() or None,
                       access_level=access_level, effective_date=effective_date, supersedes_id=supersedes_document_id)


@documents_router.post("/url", response_model=s.DocumentOut, status_code=201, dependencies=[ai_work()])
def add_url(data: s.UrlIn, ctx: OrgContext = Depends(UPLOAD), db: Session = Depends(get_db)):
    return docs.add_url(db, ctx, data.url, data.title, data.access_level)


@documents_router.get("/{doc_id}", response_model=s.DocumentDetailOut)
def get_document(doc_id: uuid.UUID, ctx: OrgContext = Depends(READ), db: Session = Depends(get_db)):
    return _detail(db, docs.get(db, ctx, doc_id))


@documents_router.get("/{doc_id}/chunks", response_model=list[s.ChunkOut])
def get_chunks(doc_id: uuid.UUID, ctx: OrgContext = Depends(READ), db: Session = Depends(get_db)):
    return docs.chunks(db, docs.get(db, ctx, doc_id))


@documents_router.patch("/{doc_id}", response_model=s.DocumentDetailOut)
def update_document(doc_id: uuid.UUID, data: s.DocumentPatch, ctx: OrgContext = Depends(REVIEW),
                    db: Session = Depends(get_db)):
    doc = docs.update(db, ctx, docs.get(db, ctx, doc_id), data.model_dump(exclude_unset=True))
    return _detail(db, doc)


@documents_router.post("/{doc_id}/versions", response_model=s.DocumentDetailOut, dependencies=[ai_work()])
async def add_version(doc_id: uuid.UUID, file: UploadFile = File(...), ctx: OrgContext = Depends(UPLOAD),
                      db: Session = Depends(get_db)):
    doc = docs.get(db, ctx, doc_id)
    data = await _read_capped(file)
    return _detail(db, docs.add_version(db, ctx, doc, file.filename or "upload", data))


@documents_router.post("/{doc_id}/retry", response_model=s.DocumentDetailOut, dependencies=[ai_work()])
def retry(doc_id: uuid.UUID, ctx: OrgContext = Depends(UPLOAD), db: Session = Depends(get_db)):
    return _detail(db, docs.retry(db, ctx, docs.get(db, ctx, doc_id)))


@documents_router.post("/{doc_id}/reprocess", response_model=s.DocumentDetailOut, dependencies=[ai_work()])
def reprocess(doc_id: uuid.UUID, ctx: OrgContext = Depends(REVIEW), db: Session = Depends(get_db)):
    return _detail(db, docs.reprocess(db, ctx, docs.get(db, ctx, doc_id)))


@documents_router.post("/{doc_id}/review", response_model=s.DocumentDetailOut)
def review(doc_id: uuid.UUID, data: s.ReviewIn, ctx: OrgContext = Depends(REVIEW), db: Session = Depends(get_db)):
    meta = data.model_dump(exclude_unset=True, exclude={"decision", "note"})
    return _detail(db, docs.review(db, ctx, docs.get(db, ctx, doc_id), data.decision, data.note, meta))


@documents_router.post("/{doc_id}/archive", response_model=s.DocumentDetailOut)
def archive(doc_id: uuid.UUID, ctx: OrgContext = Depends(REVIEW), db: Session = Depends(get_db)):
    return _detail(db, docs.archive(db, ctx, docs.get(db, ctx, doc_id)))


@documents_router.post("/{doc_id}/restore", response_model=s.DocumentDetailOut)
def restore(doc_id: uuid.UUID, ctx: OrgContext = Depends(REVIEW), db: Session = Depends(get_db)):
    return _detail(db, docs.restore(db, ctx, docs.get(db, ctx, doc_id)))


@documents_router.get("/{doc_id}/download")
def download(doc_id: uuid.UUID, version_id: uuid.UUID | None = None, ctx: OrgContext = Depends(READ),
             db: Session = Depends(get_db)):
    doc = docs.get(db, ctx, doc_id)
    version = docs.version_for_download(db, doc, version_id)
    name = doc.original_filename or f"{doc.title}.{version.detected_format}"
    return Response(get_storage().get(version.storage_key), media_type=version.mime_type, headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})


# ---- retrieval & answers ---------------------------------------------------------------------------------------

@knowledge_router.get("/status")
def status(_: OrgContext = Depends(READ)):
    return gateway.status()


@knowledge_router.post("/search", response_model=s.SearchOut, dependencies=[ai_work()])
def search(data: s.SearchIn, ctx: OrgContext = Depends(READ), db: Session = Depends(get_db)):
    found = retrieval.search(db, gateway.Caller(ctx.org_id, ctx.user.id), data.query,
                             levels=docs.allowed_levels(ctx), top_k=data.top_k, mode=data.mode)
    return s.SearchOut(hits=found.hits, sufficient=found.sufficient, mode=data.mode)


@knowledge_router.post("/ask", response_model=s.AnswerOut, dependencies=[per_user("ask_user")])
def ask(data: s.AskIn, ctx: OrgContext = Depends(require_org_permission("knowledge.ask")),
        db: Session = Depends(get_db)):
    caller = gateway.Caller(ctx.org_id, ctx.user.id)
    found = retrieval.search(db, caller, data.question, levels=docs.allowed_levels(ctx), top_k=data.top_k)
    try:
        return answering.answer(db, caller, data.question, found)
    except gateway.LLMError as exc:
        raise AppError(502 if exc.code != "not_configured" else 503, f"ai_{exc.code}", str(exc)) from exc


@knowledge_router.get("/queries", response_model=list[s.KnowledgeQueryOut])
def queries(limit: int = Query(50, ge=1, le=200), ctx: OrgContext = Depends(REVIEW), db: Session = Depends(get_db)):
    return list(db.scalars(select(KnowledgeQuery).where(KnowledgeQuery.organization_id == ctx.org_id)
                           .order_by(KnowledgeQuery.created_at.desc()).limit(limit)))


@knowledge_router.get("/evals/cases", response_model=list[s.EvalCaseOut])
def eval_cases(ctx: OrgContext = Depends(REVIEW), db: Session = Depends(get_db)):
    return list(db.scalars(select(RagEvalCase).where(RagEvalCase.organization_id == ctx.org_id)
                           .order_by(RagEvalCase.created_at)))


@knowledge_router.post("/evals/cases", response_model=s.EvalCaseOut, status_code=201)
def create_eval_case(data: s.EvalCaseIn, ctx: OrgContext = Depends(REVIEW), db: Session = Depends(get_db)):
    if not set(data.access_levels) <= set(docs.allowed_levels(ctx)):
        raise AppError(403, "forbidden", "A case can't use access levels above your own")
    body = data.model_dump(mode="json")
    case = RagEvalCase(organization_id=ctx.org_id, created_by_id=ctx.user.id, **body)
    db.add(case)
    db.commit()
    db.refresh(case)
    return case


@knowledge_router.delete("/evals/cases/{case_id}", status_code=204)
def delete_eval_case(case_id: uuid.UUID, ctx: OrgContext = Depends(REVIEW), db: Session = Depends(get_db)):
    case = db.get(RagEvalCase, case_id)
    if case is None or case.organization_id != ctx.org_id:
        raise not_found("Case")
    db.delete(case)
    db.commit()
    return Response(status_code=204)


@knowledge_router.post("/evals/runs", response_model=s.EvalRunOut, status_code=201, dependencies=[ai_work()])
def run_evals(data: s.EvalRunIn, ctx: OrgContext = Depends(REVIEW), db: Session = Depends(get_db)):
    try:
        return evals.run(db, ctx, mode=data.mode, top_k=data.top_k)
    except gateway.LLMError as exc:
        raise AppError(502, f"ai_{exc.code}", str(exc)) from exc


@knowledge_router.get("/evals/runs", response_model=list[s.EvalRunOut])
def eval_runs(ctx: OrgContext = Depends(REVIEW), db: Session = Depends(get_db)):
    return list(db.scalars(select(RagEvalRun).where(RagEvalRun.organization_id == ctx.org_id)
                           .order_by(RagEvalRun.created_at.desc()).limit(50)))


@knowledge_router.get("/evals/runs/{run_id}", response_model=s.EvalRunDetailOut)
def eval_run(run_id: uuid.UUID, ctx: OrgContext = Depends(REVIEW), db: Session = Depends(get_db)):
    run = db.get(RagEvalRun, run_id)
    if run is None or run.organization_id != ctx.org_id:
        raise not_found("Run")
    results = db.scalars(select(RagEvalResult).where(RagEvalResult.run_id == run.id)).all()
    return s.EvalRunDetailOut(**s.EvalRunOut.model_validate(run).model_dump(),
                              results=[s.EvalResultOut.model_validate(r) for r in results])


# ---- interview -------------------------------------------------------------------------------------------------

@interview_router.get("", response_model=list[s.InterviewQuestionOut])
def list_questions(ctx: OrgContext = Depends(require_org_permission("company.read")), db: Session = Depends(get_db)):
    return interview.list_questions(db, ctx.org_id)


@interview_router.post("/generate", response_model=s.InterviewGenerateOut, dependencies=[ai_work()])
def generate(ctx: OrgContext = Depends(require_org_permission("company.write")), db: Session = Depends(get_db)):
    try:
        created, label = interview.generate(db, ctx)
    except gateway.LLMError as exc:
        raise AppError(502, f"ai_{exc.code}", str(exc)) from exc
    return s.InterviewGenerateOut(created=created, label=label,
                                  questions=[s.InterviewQuestionOut.model_validate(q)
                                             for q in interview.list_questions(db, ctx.org_id)])


@interview_router.post("/{question_id}/answer", response_model=s.InterviewQuestionOut)
def answer_question(question_id: uuid.UUID, data: s.InterviewAnswerIn,
                    ctx: OrgContext = Depends(require_org_permission("company.write")), db: Session = Depends(get_db)):
    return interview.answer(db, ctx, question_id, data.answer)


@interview_router.post("/{question_id}/dismiss", response_model=s.InterviewQuestionOut)
def dismiss_question(question_id: uuid.UUID, ctx: OrgContext = Depends(require_org_permission("company.write")),
                     db: Session = Depends(get_db)):
    return interview.dismiss(db, ctx, question_id)
