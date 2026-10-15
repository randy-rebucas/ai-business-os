"""Business knowledge & RAG (SPEC §3 step 3). Only `status = 'indexed'` documents are retrievable (ADR-013)."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from abos.core.db import Base, IdMixin, TenantMixin, TimestampMixin

EMBEDDING_DIMS = 1024  # must match Settings.embedding_dimensions

DOC_STATUSES = ("uploaded", "queued", "processing", "awaiting_review", "indexed", "failed", "superseded", "archived")
ACCESS_LEVELS = ("general", "restricted", "confidential")


class Document(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (Index("ix_documents_org_status", "organization_id", "status"),)

    title: Mapped[str] = mapped_column(String(300))
    source_type: Mapped[str] = mapped_column(String(10))  # upload | url
    source_url: Mapped[str | None] = mapped_column(String(2000))
    original_filename: Mapped[str | None] = mapped_column(String(300))
    mime_type: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20), default="uploaded")
    # Classification: policy | sop | handbook | catalog | pricing | contract | financial | org_chart |
    # job_description | workflow | script | other. Proposed by the pipeline, editable by reviewers.
    doc_type: Mapped[str] = mapped_column(String(30), default="other")
    doc_type_source: Mapped[str] = mapped_column(String(10), default="auto")  # auto | reviewer
    subject: Mapped[str | None] = mapped_column(String(200))
    access_level: Mapped[str] = mapped_column(String(20), default="general")  # general | restricted | confidential
    effective_date: Mapped[date | None] = mapped_column(Date)
    summary: Mapped[str | None] = mapped_column(Text)
    summary_label: Mapped[str | None] = mapped_column(String(200))  # e.g. the dev-adapter label
    warnings: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    error_code: Mapped[str | None] = mapped_column(String(60))
    error_message: Mapped[str | None] = mapped_column(String(500))
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("document_versions.id", ondelete="SET NULL", use_alter=True))
    # When this document is approved it supersedes that one (outdated policy replaced by a new one).
    supersedes_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"))
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(Text)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DocumentVersion(IdMixin, TenantMixin, Base):
    __tablename__ = "document_versions"
    __table_args__ = (UniqueConstraint("document_id", "version_no", name="uq_document_version_no"),)

    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    version_no: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(200))
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    mime_type: Mapped[str] = mapped_column(String(120))
    detected_format: Mapped[str] = mapped_column(String(10))  # pdf | docx | xlsx | csv | txt | md | html
    scan_status: Mapped[str] = mapped_column(String(20), default="not_scanned")  # not_scanned | clean | infected
    page_count: Mapped[int | None] = mapped_column(Integer)
    char_count: Mapped[int | None] = mapped_column(Integer)
    ocr_used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DocumentChunk(IdMixin, TenantMixin, Base):
    """Only the current version's chunks exist; re-indexing replaces them (versions keep the originals)."""

    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("version_id", "chunk_index", name="uq_chunk_version_index"),
        Index("ix_chunks_tsv", "tsv", postgresql_using="gin"),
        Index("ix_chunks_embedding", "embedding", postgresql_using="hnsw",
              postgresql_with={"m": 16, "ef_construction": 64}, postgresql_ops={"embedding": "vector_cosine_ops"}),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document_versions.id", ondelete="CASCADE"))
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    section: Mapped[str | None] = mapped_column(String(500))  # heading path "Refunds > Over the limit"
    page_number: Mapped[int | None] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(10), default="text")  # text | table
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    flags: Mapped[list[str]] = mapped_column(JSONB, default=list)  # e.g. ["instruction_like_text"]
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMS))
    tsv: Mapped[Any] = mapped_column(TSVECTOR, Computed("to_tsvector('english', content)", persisted=True))
    indexed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class JobRun(IdMixin, TimestampMixin, TenantMixin, Base):
    """Durable state of a background job (ADR-008). Redis only carries the wake-up message."""

    __tablename__ = "job_runs"
    __table_args__ = (Index("ix_job_runs_status", "status", "updated_at"),)

    kind: Mapped[str] = mapped_column(String(40))  # ingest_document
    target_id: Mapped[uuid.UUID] = mapped_column(index=True)
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued | running | succeeded | failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    last_error: Mapped[str | None] = mapped_column(String(500))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)  # pipeline progress log


class KnowledgeQuery(IdMixin, TenantMixin, Base):
    """Every question answered from company knowledge, with exactly what was retrieved and cited (evidence)."""

    __tablename__ = "knowledge_queries"
    __table_args__ = (Index("ix_knowledge_queries_org_created", "organization_id", "created_at"),)

    question: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30))  # answered | insufficient_evidence | conflicting | unsupported
    answer: Mapped[str] = mapped_column(Text)
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    retrieved: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)  # chunk ids + scores
    checks: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)  # citation / unsupported-claim results
    provider: Mapped[str] = mapped_column(String(30))
    model: Mapped[str] = mapped_column(String(80))
    asked_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RagEvalCase(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "rag_eval_cases"

    question: Mapped[str] = mapped_column(Text)
    # normal | outdated | conflicting | inaccessible | missing | injection
    category: Mapped[str] = mapped_column(String(20), default="normal")
    # answered | insufficient_evidence | conflicting
    expected_status: Mapped[str] = mapped_column(String(30), default="answered")
    expected_answer_contains: Mapped[list[str]] = mapped_column(JSONB, default=list)
    expected_document_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    forbidden_document_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    forbidden_phrases: Mapped[list[str]] = mapped_column(JSONB, default=list)
    access_levels: Mapped[list[str]] = mapped_column(JSONB, default=lambda: ["general"])
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class RagEvalRun(IdMixin, TenantMixin, Base):
    __tablename__ = "rag_eval_runs"

    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)  # mode, top_k, provider, embeddings
    status: Mapped[str] = mapped_column(String(20), default="completed")
    case_count: Mapped[int] = mapped_column(Integer, default=0)
    passed_count: Mapped[int] = mapped_column(Integer, default=0)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RagEvalResult(IdMixin, TenantMixin, Base):
    __tablename__ = "rag_eval_results"

    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rag_eval_runs.id", ondelete="CASCADE"), index=True)
    case_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("rag_eval_cases.id", ondelete="SET NULL"))
    question: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(20))
    passed: Mapped[bool] = mapped_column(Boolean)
    status: Mapped[str] = mapped_column(String(30))
    answer: Mapped[str] = mapped_column(Text)
    retrieved_document_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    reciprocal_rank: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=0)
    precision: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=0)
    checks: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)  # name -> {passed, detail}
    failure_reasons: Mapped[list[str]] = mapped_column(JSONB, default=list)


class InterviewQuestion(IdMixin, TimestampMixin, TenantMixin, Base):
    """AI-guided business interview: follow-up questions generated from profile gaps and answers (SPEC step 1)."""

    __tablename__ = "interview_questions"
    __table_args__ = (UniqueConstraint("organization_id", "topic_key", name="uq_interview_org_topic"),)

    topic_key: Mapped[str] = mapped_column(String(80))  # stable id so regeneration doesn't duplicate questions
    section: Mapped[str] = mapped_column(String(30))
    question: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(10), default="rule")  # rule | model | dev
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | answered | dismissed
    answer: Mapped[str | None] = mapped_column(Text)
    answered_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
