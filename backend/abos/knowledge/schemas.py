import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

AccessLevel = Literal["general", "restricted", "confidential"]
DocType = Literal["policy", "sop", "handbook", "catalog", "pricing", "contract", "financial", "org_chart",
                  "job_description", "workflow", "script", "other"]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class VersionOut(ORM):
    id: uuid.UUID
    version_no: int
    sha256: str
    size_bytes: int
    mime_type: str
    detected_format: str
    scan_status: str
    page_count: int | None
    char_count: int | None
    ocr_used: bool
    created_at: datetime


class JobOut(ORM):
    id: uuid.UUID
    status: str
    attempts: int
    max_attempts: int
    last_error: str | None
    steps: list[dict[str, Any]]
    created_at: datetime
    finished_at: datetime | None


class DocumentOut(ORM):
    id: uuid.UUID
    title: str
    source_type: str
    source_url: str | None
    original_filename: str | None
    mime_type: str | None
    status: str
    doc_type: str
    doc_type_source: str
    subject: str | None
    access_level: str
    effective_date: date | None
    summary: str | None
    summary_label: str | None
    warnings: list[dict[str, Any]]
    error_code: str | None
    error_message: str | None
    chunk_count: int
    supersedes_document_id: uuid.UUID | None
    uploaded_by_id: uuid.UUID | None
    reviewed_by_id: uuid.UUID | None
    reviewed_at: datetime | None
    review_note: str | None
    indexed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class DocumentDetailOut(DocumentOut):
    versions: list[VersionOut]
    latest_job: JobOut | None
    superseded_by: list[dict[str, Any]] = []


class ChunkOut(ORM):
    id: uuid.UUID
    chunk_index: int
    section: str | None
    page_number: int | None
    kind: str
    content: str
    flags: list[str]
    token_count: int


class UrlIn(BaseModel):
    url: Annotated[str, StringConstraints(strip_whitespace=True, min_length=8, max_length=2000)]
    title: Title | None = None
    access_level: AccessLevel = "general"


class DocumentPatch(BaseModel):
    title: Title | None = None
    doc_type: DocType | None = None
    access_level: AccessLevel | None = None
    effective_date: date | None = None
    supersedes_document_id: uuid.UUID | None = None


class ReviewIn(BaseModel):
    decision: Literal["approve", "reject"]
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] | None = None
    doc_type: DocType | None = None
    access_level: AccessLevel | None = None
    effective_date: date | None = None


# ---- retrieval & answers ---------------------------------------------------------------------------------------

class SearchIn(BaseModel):
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=1000)]
    top_k: int = Field(8, ge=1, le=20)
    mode: Literal["hybrid", "vector", "keyword"] = "hybrid"


class SearchHit(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    doc_type: str
    access_level: str
    effective_date: date | None
    version_no: int
    section: str | None
    page_number: int | None
    content: str
    score: float
    vector_score: float | None
    keyword_score: float | None
    vector_rank: int | None
    keyword_rank: int | None
    flags: list[str]


class SearchOut(BaseModel):
    hits: list[SearchHit]
    sufficient: bool
    mode: str


class AskIn(BaseModel):
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=2000)]
    top_k: int = Field(8, ge=1, le=20)


class Citation(BaseModel):
    source: str  # S1, S2 … as shown to the model
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    section: str | None
    page_number: int | None
    version_no: int
    quote: str


class AnswerOut(BaseModel):
    id: uuid.UUID
    question: str
    status: Literal["answered", "insufficient_evidence", "conflicting", "unsupported"]
    answer: str
    citations: list[Citation]
    conflicts: list[str]
    follow_up_question: str | None
    checks: dict[str, Any]
    provider: str
    model: str
    label: str | None
    sources: list[SearchHit]


# ---- evaluation ------------------------------------------------------------------------------------------------

Phrase = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class EvalCaseIn(BaseModel):
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=2000)]
    category: Literal["normal", "outdated", "conflicting", "inaccessible", "missing", "injection"] = "normal"
    expected_status: Literal["answered", "insufficient_evidence", "conflicting"] = "answered"
    expected_answer_contains: Annotated[list[Phrase], Field(max_length=10)] = []
    expected_document_ids: Annotated[list[uuid.UUID], Field(max_length=10)] = []
    forbidden_document_ids: Annotated[list[uuid.UUID], Field(max_length=10)] = []
    forbidden_phrases: Annotated[list[Phrase], Field(max_length=10)] = []
    access_levels: Annotated[list[AccessLevel], Field(min_length=1, max_length=3)] = ["general"]
    notes: Annotated[str, StringConstraints(max_length=2000)] | None = None


class EvalCaseOut(ORM):
    id: uuid.UUID
    question: str
    category: str
    expected_status: str
    expected_answer_contains: list[str]
    expected_document_ids: list[str]
    forbidden_document_ids: list[str]
    forbidden_phrases: list[str]
    access_levels: list[str]
    notes: str | None
    created_at: datetime


class EvalRunIn(BaseModel):
    mode: Literal["hybrid", "vector", "keyword"] = "hybrid"
    top_k: int = Field(5, ge=1, le=20)


class EvalResultOut(ORM):
    id: uuid.UUID
    case_id: uuid.UUID | None
    question: str
    category: str
    passed: bool
    status: str
    answer: str
    retrieved_document_ids: list[str]
    reciprocal_rank: Decimal
    precision: Decimal
    checks: dict[str, Any]
    failure_reasons: list[str]


class EvalRunOut(ORM):
    id: uuid.UUID
    config: dict[str, Any]
    status: str
    case_count: int
    passed_count: int
    metrics: dict[str, Any]
    created_at: datetime


class EvalRunDetailOut(EvalRunOut):
    results: list[EvalResultOut]


class KnowledgeQueryOut(ORM):
    id: uuid.UUID
    question: str
    status: str
    answer: str
    citations: list[dict[str, Any]]
    provider: str
    model: str
    asked_by_id: uuid.UUID | None
    created_at: datetime


# ---- interview -------------------------------------------------------------------------------------------------

class InterviewQuestionOut(ORM):
    id: uuid.UUID
    topic_key: str
    section: str
    question: str
    rationale: str | None
    source: str
    status: str
    answer: str | None
    answered_at: datetime | None
    created_at: datetime


class InterviewAnswerIn(BaseModel):
    answer: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)]


class InterviewGenerateOut(BaseModel):
    created: int
    questions: list[InterviewQuestionOut]
    label: str | None
