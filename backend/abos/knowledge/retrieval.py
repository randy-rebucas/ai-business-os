"""Hybrid retrieval (SPEC §3 step 3): pgvector cosine similarity + Postgres full-text, fused with reciprocal rank
fusion (RRF). Authorization is part of the SQL — organization, `indexed` status, current version and the caller's
access levels — so unauthorised text is never fetched, let alone shown to a model. RLS applies underneath.

Exact identifiers (invoice numbers, SKUs, policy codes) are matched by the keyword side: vector similarity alone
does not find "INV-2041" reliably.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from abos.core.config import get_settings
from abos.knowledge.schemas import SearchHit
from abos.llm import gateway

RRF_K = 60

_FILTER = """
    c.organization_id = :org
    AND d.organization_id = :org
    AND d.status = 'indexed'
    AND c.version_id = d.current_version_id
    AND d.access_level = ANY(:levels)
    AND (CAST(:doc_ids AS uuid[]) IS NULL OR d.id = ANY(CAST(:doc_ids AS uuid[])))
"""

_VECTOR_SQL = text(f"""
    SELECT c.id, 1 - (c.embedding <=> CAST(:q AS vector)) AS score
    FROM document_chunks c JOIN documents d ON d.id = c.document_id
    WHERE {_FILTER}
    ORDER BY c.embedding <=> CAST(:q AS vector)
    LIMIT :n
""")  # noqa: S608 — _FILTER is a constant; all values are bound parameters

_KEYWORD_SQL = text(f"""
    SELECT c.id, ts_rank_cd(c.tsv, query, 32) AS score
    FROM document_chunks c JOIN documents d ON d.id = c.document_id,
         websearch_to_tsquery('english', :q) query
    WHERE {_FILTER} AND c.tsv @@ query
    ORDER BY score DESC
    LIMIT :n
""")  # noqa: S608

# Fallback when the strict (AND) web-search query matches nothing: any of the terms (OR).
_KEYWORD_ANY_SQL = text(f"""
    SELECT c.id, ts_rank_cd(c.tsv, query, 32) AS score
    FROM document_chunks c JOIN documents d ON d.id = c.document_id,
         to_tsquery('english', :q) query
    WHERE {_FILTER} AND c.tsv @@ query
    ORDER BY score DESC
    LIMIT :n
""")  # noqa: S608

_DETAILS_SQL = text("""
    SELECT c.id AS chunk_id, c.document_id, d.title AS document_title, d.doc_type, d.access_level,
           d.effective_date, v.version_no, c.section, c.page_number, c.content, c.flags
    FROM document_chunks c
    JOIN documents d ON d.id = c.document_id
    JOIN document_versions v ON v.id = c.version_id
    WHERE c.id = ANY(:ids)
""")


@dataclass
class Retrieval:
    hits: list[SearchHit]
    sufficient: bool


def _any_terms_query(q: str) -> str | None:
    words = [w for w in "".join(ch if ch.isalnum() else " " for ch in q.lower()).split() if len(w) > 2]
    return " | ".join(dict.fromkeys(words)) or None


def search(db: Session, caller: gateway.Caller, query: str, *, levels: list[str], top_k: int = 8,
           mode: str = "hybrid", document_ids: list[uuid.UUID] | None = None) -> Retrieval:
    s = get_settings()
    params = {"org": caller.org_id, "levels": levels, "n": s.retrieval_candidates,
              "doc_ids": [str(d) for d in document_ids] if document_ids else None}
    vec: dict[uuid.UUID, tuple[int, float]] = {}
    kw: dict[uuid.UUID, tuple[int, float]] = {}
    if mode in ("hybrid", "vector"):
        qv = gateway.embed(caller, [query], input_type="query", purpose="embed_query").vectors[0]
        db.execute(text("SET LOCAL hnsw.iterative_scan = 'relaxed_order'"))  # keep filtering exact under HNSW
        rows = db.execute(_VECTOR_SQL, {**params, "q": str(qv)}).all()
        vec = {r.id: (i + 1, float(r.score)) for i, r in enumerate(rows)}
    if mode in ("hybrid", "keyword"):
        rows = db.execute(_KEYWORD_SQL, {**params, "q": query}).all()
        if not rows and (anyq := _any_terms_query(query)):
            rows = db.execute(_KEYWORD_ANY_SQL, {**params, "q": anyq}).all()
        kw = {r.id: (i + 1, float(r.score)) for i, r in enumerate(rows)}

    # Relevance (step 7): nearest-neighbour search always returns *something*, so a vector-only candidate must clear
    # the similarity threshold to count. Irrelevant chunks are dropped rather than shown to a model as "sources".
    relevant = set(kw) | {cid for cid, (_, score) in vec.items() if score >= s.retrieval_min_vector_score}
    fused: dict[uuid.UUID, float] = {}
    for ranks in (vec, kw):
        for cid, (rank, _) in ranks.items():
            if cid in relevant:
                fused[cid] = fused.get(cid, 0.0) + 1.0 / (RRF_K + rank)
    order = sorted(fused, key=lambda c: fused[c], reverse=True)[:top_k]
    if not order:
        return Retrieval([], False)
    details = {r.chunk_id: r for r in db.execute(_DETAILS_SQL, {"ids": order}).mappings()}
    hits = []
    for cid in order:
        d = details[cid]
        hits.append(SearchHit(**d, score=round(fused[cid], 6),
                              vector_score=round(vec[cid][1], 4) if cid in vec else None,
                              keyword_score=round(kw[cid][1], 4) if cid in kw else None,
                              vector_rank=vec[cid][0] if cid in vec else None,
                              keyword_rank=kw[cid][0] if cid in kw else None))
    return Retrieval(hits, sufficient=bool(hits))
