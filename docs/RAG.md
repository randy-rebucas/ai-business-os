# RAG ingestion & retrieval pipeline

Implements SPEC §3 step 3. Code: `backend/abos/knowledge/`, `backend/abos/llm/`, `backend/abos/jobs/`.

## Document lifecycle

```
upload / URL ──► uploaded ─► queued ─► processing ─► awaiting_review ──approve──► indexed  (retrievable)
                                 ▲          │                    └──reject───► archived
                                 └─retry── failed                indexed ──new version / reprocess──► queued
                                                                 indexed ──newer doc approved with "replaces"──► superseded
```
Only `indexed` documents are retrievable (ADR-013). A new version or reprocess sends the document back through
review. Every file version is kept (`document_versions`); only the current version's chunks exist.

## The 12 steps

| # | Step | Where | Notes |
|---|---|---|---|
| 1 | Validate | `parsing.sniff`, `documents.upload` | Type from the bytes (magic numbers, ZIP members, text decode), extension must agree; 20 MB cap (middleware + route); binary-in-text rejected |
| 2 | Store | `storage.py` | Private object storage, key `{org}/{doc}/v{n}` built server-side; SHA-256 recorded and re-checked before parsing |
| 3 | Extract | `parsing.py` | PDF (pypdf, per page), DOCX (headings by style, tables), XLSX (sheet → table, 5000 rows), CSV, TXT, Markdown, HTML (URL imports; scripts/nav/forms dropped) |
| 4 | OCR | `ocr.py` | Tesseract when installed. Without it, empty pages produce an `ocr_unavailable` warning, or `no_text_ocr_unavailable` failure if nothing is readable — never a silent success |
| 5 | Normalise | `parsing.clean` | NFC, control chars removed, whitespace collapsed, tables kept as rows |
| 6 | Classify | `chunking.classify` | Keyword rules → policy / sop / handbook / pricing / …; reviewers override (kept on reprocess) |
| 7 | Chunk | `chunking.chunk` | Never crosses a heading; ~900 chars target / 1600 max; tables split by rows with the header repeated; heading path stored as `section` and prefixed to the text |
| 8 | Embed | `llm.gateway.embed` | 1024-dim, L2-normalised; batches of 64; usage recorded |
| 9 | Index | `ingest.py` | pgvector HNSW (cosine) + generated `tsvector` (GIN); old chunks replaced in the same transaction |
| 10 | Metadata & permissions | `document_chunks`, `documents` | org, document, version, section, page, kind, flags; access level + status + effective date live on the document and are joined in every query |
| 11 | Validate index | `ingest._validate_index` | Row count matches; the first chunk is found by a vector search restricted to the document |
| 12 | Make available | `documents.review` | A person approves → `indexed` |

Long work runs in the `ingest_document` background job (Celery + Redis, durable state in `job_runs`, ADR-008):
transient failures retry up to 3 attempts; permanent ones (bad file) fail immediately with a code and message the
UI shows; `retry` re-queues. Each step is committed to `job_runs.steps` so the UI shows live progress.

## Query execution

1. **Who / which org / which agent** — `gateway.Caller` (org, user, later agent instance).
2. **Permitted sources** — `documents.allowed_levels`: general for all; restricted for `knowledge.review`;
   confidential for `knowledge.confidential`. Agents get explicit scopes in Phase 3.
3. **Retrieval queries** — the question as typed (query rewriting is a later improvement).
4. **Filtered retrieval** — `retrieval.search`: org, `indexed`, current version and access level are in the SQL of
   both retrievers; RLS underneath. `hnsw.iterative_scan` keeps filtered HNSW results complete.
5. **Combine** — vector (cosine) + keyword (`websearch_to_tsquery`, falling back to any-term) fused with RRF (k=60).
   Keyword retrieval is what finds exact identifiers such as `PX-2042`.
6. **Rerank** — not implemented (optional in the spec).
7. **Relevance & sufficiency** — a candidate counts only if it matched by keyword or has cosine ≥
   `ABOS_RETRIEVAL_MIN_VECTOR_SCORE`; no relevant hits → "insufficient evidence" without calling a model.
8. **Evidence to the model** — numbered `<source>` blocks with document, version, section, page, effective date;
   instruction-like sentences replaced with a placeholder (`safety.redact`).
9. **Grounded response** — JSON schema output: status, answer, citations (source id + verbatim quote), conflicts,
   follow-up question. The system prompt treats sources as untrusted data.
10. **Citations, verified** — `answer._verify`: unknown source ids and quotes not found in the source are dropped;
    figures in the answer must appear in the sources; otherwise the status becomes `unsupported` and the UI says not
    to rely on it. Every answer is stored in `knowledge_queries` with what was retrieved and cited.

## Evaluation

`/app/knowledge/evals` — cases with category (normal, outdated, conflicting, inaccessible, missing, injection),
expected status, phrases the answer must / must never contain, expected and forbidden documents, and the access
levels to ask with. Runs execute the real retrieval + answer path and grade deterministically: status, expected
phrases, expected source retrieved (rank → MRR, hit rate) and cited, precision, citation validity, unsupported
figures, plus **security checks** (forbidden document retrieved, forbidden phrase answered) that fail a case
regardless of the rest. Runs record their configuration (mode, top-k, providers) for comparison.

## Providers

| Purpose | Dev (default) | Real | Verified live? |
|---|---|---|---|
| Embeddings | `hash` — lexical feature hashing, labelled | `voyage`, `openai`-compatible | **No** — adapters written to the documented HTTP APIs, untested |
| Answers / summaries / interview | `dev` — extractive, labelled "Development adapter" | `anthropic` (Claude Opus 5.5, JSON schema output, refusal fallbacks) | **No** — request shape unit-tested with a fake client; no billed call made |
| OCR | unavailable | Tesseract via `.[ocr]` | **No** |

Changing the embedding provider changes the vector space: reprocess every document afterwards
(`POST /documents/{id}/reprocess`, then review). Production refuses to start with the dev adapters.
