"""Provider-independent LLM gateway (ADR-012). The only module that talks to model providers.

`complete_json` returns schema-shaped JSON for one task. Every task supplies a `dev` function: with
ABOS_LLM_PROVIDER=dev that deterministic function runs instead of a model, and the result is labelled
"Development adapter" — it never pretends to be a model. With `anthropic`, Claude is called with a JSON-schema
output format, adaptive thinking (always on for Opus 5.5) at the configured effort, and server-side refusal
fallbacks. Every call — success, error or refusal — is written to `model_usage` in its own transaction.
"""

import json
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from typing import Any

from abos.core.config import get_settings
from abos.core.db import SessionLocal
from abos.core.tenancy import set_tenant
from abos.llm import embeddings as emb
from abos.llm.models import ModelUsage

log = logging.getLogger("abos.llm")

DEV_LABEL = "Development adapter — deterministic output, no AI model was called"

# USD per 1M tokens (input, output). Estimates for the usage ledger; the provider invoice is authoritative.
PRICES: dict[str, tuple[Decimal, Decimal]] = {
    "claude-opus-5-5": (Decimal(4), Decimal(20)),
    "claude-sonnet-5-5": (Decimal(2), Decimal(10)),
    "claude-haiku-5-5": (Decimal("0.10"), Decimal("0.50")),
    "claude-fable-5-1": (Decimal(10), Decimal(50)),
    "voyage-3.5": (Decimal("0.06"), Decimal(0)),
}


class LLMError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass
class LLMResult:
    data: dict[str, Any]
    provider: str
    model: str
    is_dev: bool
    label: str | None  # shown to users whenever the dev adapter produced the output


@dataclass
class Caller:
    org_id: uuid.UUID
    user_id: uuid.UUID | None = None
    agent_instance_id: uuid.UUID | None = None


def _cost(model: str, inp: int, out: int) -> Decimal:
    pi, po = PRICES.get(model, (Decimal(0), Decimal(0)))
    return (pi * inp + po * out) / Decimal(1_000_000)


def record_usage(caller: Caller, *, purpose: str, provider: str, model: str, input_tokens: int = 0,
                 output_tokens: int = 0, latency_ms: int = 0, status: str = "ok", error_code: str | None = None,
                 request_id: str | None = None) -> None:
    """Own session + commit: usage survives even when the caller's transaction rolls back."""
    with SessionLocal() as db:
        set_tenant(db, caller.org_id)
        db.add(ModelUsage(organization_id=caller.org_id, purpose=purpose, provider=provider, model=model,
                          input_tokens=input_tokens, output_tokens=output_tokens,
                          cost_usd=_cost(model, input_tokens, output_tokens), latency_ms=latency_ms, status=status,
                          error_code=error_code, request_id=request_id, actor_user_id=caller.user_id,
                          agent_instance_id=caller.agent_instance_id))
        db.commit()


@lru_cache
def _anthropic_client():
    import anthropic  # noqa: PLC0415 — only imported when the provider is used

    s = get_settings()
    return anthropic.Anthropic(api_key=s.anthropic_api_key.get_secret_value() if s.anthropic_api_key else None,
                               timeout=s.llm_timeout_seconds, max_retries=2)


def _call_anthropic(model: str, system: str, user: str, schema: dict) -> tuple[dict, int, int, str | None]:
    import anthropic  # noqa: PLC0415

    s = get_settings()
    try:
        response = _anthropic_client().beta.messages.create(
            model=model,
            max_tokens=s.llm_max_output_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"effort": s.llm_effort, "format": {"type": "json_schema", "schema": schema}},
            betas=["server-side-fallback-2026-07-01"],
            extra_body={"fallbacks": "default"},  # re-run on a fallback model if a safety classifier declines
        )
    except anthropic.RateLimitError as exc:
        raise LLMError("rate_limited", "The AI provider is rate limiting requests; try again shortly") from exc
    except anthropic.APIStatusError as exc:
        raise LLMError("provider_error", f"AI provider error ({exc.status_code})") from exc
    except anthropic.APIConnectionError as exc:
        raise LLMError("provider_unreachable", "The AI provider could not be reached") from exc
    usage = response.usage
    rid = getattr(response, "_request_id", None)
    if response.stop_reason == "refusal":
        raise LLMError("refusal", "The AI model declined this request")
    if response.stop_reason == "max_tokens":
        raise LLMError("truncated", "The AI response was cut off before it finished")
    text = next((b.text for b in response.content if b.type == "text"), None)
    if text is None:
        raise LLMError("empty_response", "The AI model returned no answer")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMError("invalid_json", "The AI model returned malformed output") from exc
    return data, usage.input_tokens, usage.output_tokens, rid


def complete_json(caller: Caller, *, purpose: str, system: str, user: str, schema: dict,
                  dev: Callable[[], dict], analysis: bool = False) -> LLMResult:
    s = get_settings()
    if s.llm_provider == "dev":
        data = dev()
        record_usage(caller, purpose=purpose, provider="dev", model="dev-deterministic")
        return LLMResult(data, "dev", "dev-deterministic", True, DEV_LABEL)
    if not s.llm_configured:
        raise LLMError("not_configured", "ABOS_ANTHROPIC_API_KEY is not set")
    model = s.llm_analysis_model if analysis else s.llm_model
    start = time.perf_counter()
    try:
        data, inp, out, rid = _call_anthropic(model, system, user, schema)
    except LLMError as exc:
        record_usage(caller, purpose=purpose, provider="anthropic", model=model,
                     latency_ms=int((time.perf_counter() - start) * 1000),
                     status="refusal" if exc.code == "refusal" else "error", error_code=exc.code)
        log.warning("llm_error", extra={"fields": {"purpose": purpose, "code": exc.code}})
        raise
    record_usage(caller, purpose=purpose, provider="anthropic", model=model, input_tokens=inp, output_tokens=out,
                 latency_ms=int((time.perf_counter() - start) * 1000), request_id=rid)
    return LLMResult(data, "anthropic", model, False, None)


def embed(caller: Caller, texts: list[str], *, input_type: emb.InputType, purpose: str) -> emb.EmbeddingResult:
    s = get_settings()
    start = time.perf_counter()
    try:
        result = emb.embed(s, texts, input_type)
    except emb.EmbeddingError as exc:
        record_usage(caller, purpose=purpose, provider=s.embedding_provider, model=s.embedding_model,
                     status="error", error_code=exc.code, latency_ms=int((time.perf_counter() - start) * 1000))
        raise LLMError(exc.code, str(exc)) from exc
    record_usage(caller, purpose=purpose, provider=result.provider, model=result.model, input_tokens=result.tokens,
                 latency_ms=int((time.perf_counter() - start) * 1000))
    return result


def status() -> dict:
    s = get_settings()
    return {
        "llm": {"provider": s.llm_provider, "model": s.llm_model if s.llm_provider != "dev" else "dev-deterministic",
                "configured": s.llm_configured, "dev_adapter": s.llm_provider == "dev"},
        "embeddings": {"provider": s.embedding_provider, "configured": s.embeddings_configured,
                       "dimensions": s.embedding_dimensions, "dev_adapter": s.embedding_provider == "hash"},
    }
