"""Embedding providers (ADR-012). All return L2-normalised vectors of `embedding_dimensions` (1024).

- `hash` — development adapter: signed feature hashing of word unigrams + bigrams. Deterministic and free; it
  captures lexical overlap only (no semantics). Never allowed in production (config guard).
- `voyage` — Voyage AI embeddings API (Anthropic's recommended embedding partner).
- `openai` — any OpenAI-compatible /embeddings endpoint (set ABOS_EMBEDDING_BASE_URL for self-hosted models).
The real adapters are implemented against the providers' documented HTTP APIs but are NOT live-verified yet.
"""

import hashlib
import math
import re
from dataclasses import dataclass
from typing import Literal

import httpx

from abos.core.config import Settings

InputType = Literal["document", "query"]
_WORD = re.compile(r"[a-z0-9]+(?:[-_.][a-z0-9]+)*")


class EmbeddingError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass
class EmbeddingResult:
    vectors: list[list[float]]
    provider: str
    model: str
    tokens: int


def _normalise(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def tokens(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def hash_embed(text: str, dims: int) -> list[float]:
    vec = [0.0] * dims
    words = tokens(text)
    features = words + [f"{a} {b}" for a, b in zip(words, words[1:], strict=False)]
    for f in features:
        h = hashlib.blake2b(f.encode(), digest_size=8).digest()
        idx = int.from_bytes(h[:4], "little") % dims
        vec[idx] += 1.0 if h[4] & 1 else -1.0
    return _normalise(vec)


def _check(vectors: list[list[float]], dims: int, n: int) -> list[list[float]]:
    if len(vectors) != n or any(len(v) != dims for v in vectors):
        raise EmbeddingError("bad_dimensions", f"Provider returned vectors that are not {n}x{dims}")
    return [_normalise(v) for v in vectors]


def embed(s: Settings, texts: list[str], input_type: InputType) -> EmbeddingResult:
    dims = s.embedding_dimensions
    if not texts:
        return EmbeddingResult([], s.embedding_provider, s.embedding_model, 0)
    if s.embedding_provider == "hash":
        return EmbeddingResult([hash_embed(t, dims) for t in texts], "hash", "feature-hash-v1",
                               sum(len(tokens(t)) for t in texts))
    if not s.embeddings_configured:
        raise EmbeddingError("not_configured", "ABOS_EMBEDDING_API_KEY is not set")
    key = s.embedding_api_key.get_secret_value()  # type: ignore[union-attr]
    try:
        if s.embedding_provider == "voyage":
            r = httpx.post("https://api.voyageai.com/v1/embeddings", timeout=60,
                           headers={"Authorization": f"Bearer {key}"},
                           json={"input": texts, "model": s.embedding_model, "input_type": input_type,
                                 "output_dimension": dims})
        else:
            base = (s.embedding_base_url or "https://api.openai.com/v1").rstrip("/")
            r = httpx.post(f"{base}/embeddings", timeout=60, headers={"Authorization": f"Bearer {key}"},
                           json={"input": texts, "model": s.embedding_model, "dimensions": dims})
        r.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise EmbeddingError("provider_error", f"Embedding provider returned {exc.response.status_code}") from exc
    except httpx.HTTPError as exc:
        raise EmbeddingError("provider_unreachable", f"Embedding provider unreachable: {type(exc).__name__}") from exc
    body = r.json()
    data = sorted(body["data"], key=lambda d: d["index"])
    usage = body.get("usage") or {}
    return EmbeddingResult(_check([d["embedding"] for d in data], dims, len(texts)), s.embedding_provider,
                           s.embedding_model, int(usage.get("total_tokens") or 0))
