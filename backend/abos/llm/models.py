import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from abos.core.db import Base, IdMixin, TenantMixin


class ModelUsage(IdMixin, TenantMixin, Base):
    """Append-only ledger of every model / embedding call, written in its own transaction so a failed request still
    leaves its cost on record. Source of truth for usage & cost tracking (Phase 6)."""

    __tablename__ = "model_usage"
    __table_args__ = (Index("ix_model_usage_org_created", "organization_id", "created_at"),)

    purpose: Mapped[str] = mapped_column(String(40))  # rag_answer | document_summary | interview | embed_document …
    provider: Mapped[str] = mapped_column(String(30))  # dev | anthropic | hash | voyage | openai
    model: Mapped[str] = mapped_column(String(80))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="ok")  # ok | error | refusal
    error_code: Mapped[str | None] = mapped_column(String(60))
    request_id: Mapped[str | None] = mapped_column(String(80))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    agent_instance_id: Mapped[uuid.UUID | None] = mapped_column()  # FK added when agents exist (Phase 3)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
