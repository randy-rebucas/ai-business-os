"""Hybrid retrieval and source-grounded answers (SPEC §3 RAG query execution, §9 RAG quality tests)."""

import uuid

from sqlalchemy import select

from abos.knowledge import answer as answering
from abos.knowledge.models import KnowledgeQuery
from abos.knowledge.schemas import SearchHit
from abos.llm.models import ModelUsage
from tests.conftest import approve, indexed, upload
from tests.fixtures import LEAVE_POLICY, PRICE_LIST_CSV, REFUND_POLICY, REFUND_POLICY_OLD


def ask(actor, question):
    r = actor.post("/api/v1/knowledge/ask", json={"question": question})
    assert r.status_code == 200, r.text
    return r.json()


def test_unreviewed_documents_are_not_retrievable(owner):
    doc = upload(owner, "refunds.md", REFUND_POLICY)
    r = owner.post("/api/v1/knowledge/search", json={"query": "refund approval limit"})
    assert r.json()["hits"] == []
    approve(owner, doc)
    hits = owner.post("/api/v1/knowledge/search", json={"query": "refund approval limit"}).json()["hits"]
    assert hits and hits[0]["document_id"] == doc["id"]


def test_question_answering_with_verified_citations(owner, db):
    doc = indexed(owner, "refunds.md", REFUND_POLICY)
    indexed(owner, "leave.md", LEAVE_POLICY)
    a = ask(owner, "Who must approve refunds above 5,000 PHP?")
    assert a["status"] == "answered", a
    assert "Finance Manager" in a["answer"]
    assert a["label"].startswith("Development adapter")
    c = a["citations"][0]
    assert c["document_id"] == doc["id"] and c["section"] == "Refund Policy > Refunds above the limit"
    assert c["quote"] in next(s["content"] for s in a["sources"] if s["chunk_id"] == c["chunk_id"])
    assert a["checks"]["invalid_citations"] == [] and a["checks"]["unsupported_numbers"] == []
    # The question, answer and evidence are recorded; model use is in the ledger.
    q = db.get(KnowledgeQuery, uuid.UUID(a["id"]))
    assert q.status == "answered" and q.citations[0]["chunk_id"] == c["chunk_id"]
    assert db.scalar(select(ModelUsage).where(ModelUsage.purpose == "rag_answer")).provider == "dev"


def test_exact_identifiers_are_found_by_keyword_retrieval(owner):
    doc = indexed(owner, "prices.csv", PRICE_LIST_CSV)
    indexed(owner, "refunds.md", REFUND_POLICY)
    hits = owner.post("/api/v1/knowledge/search", json={"query": "PX-2042"}).json()["hits"]
    assert hits[0]["document_id"] == doc["id"] and hits[0]["keyword_rank"] == 1
    assert "PX-2042" in hits[0]["content"]


def test_missing_information_is_disclosed_without_calling_a_model(owner, db):
    indexed(owner, "refunds.md", REFUND_POLICY)
    a = ask(owner, "What is our parental leave policy for contractors in Singapore?")
    assert a["status"] == "insufficient_evidence" and a["citations"] == []
    assert a["provider"] in ("none", "dev")


def test_conflicting_policies_are_reported_not_resolved(owner):
    indexed(owner, "refunds-2026.md", REFUND_POLICY)
    indexed(owner, "refunds-2023.md", REFUND_POLICY_OLD)
    a = ask(owner, "Up to what amount can customer support approve refunds automatically?")
    assert a["status"] == "conflicting", a
    assert len({c["document_id"] for c in a["citations"]}) == 2


def test_superseded_documents_drop_out_of_retrieval(owner):
    old = indexed(owner, "refunds-2023.md", REFUND_POLICY_OLD)
    new = upload(owner, "refunds-2026.md", REFUND_POLICY, supersedes_document_id=old["id"])
    approve(owner, new)
    assert owner.get(f"/api/v1/documents/{old['id']}").json()["status"] == "superseded"
    a = ask(owner, "Up to what amount can customer support approve refunds automatically?")
    assert a["status"] == "answered" and "5,000" in a["answer"]
    assert {c["document_id"] for c in a["citations"]} == {new["id"]}


def test_retrieval_modes(owner):
    indexed(owner, "refunds.md", REFUND_POLICY)

    def hits(query, mode):
        r = owner.post("/api/v1/knowledge/search", json={"query": query, "mode": mode})
        assert r.status_code == 200
        return r.json()["hits"]

    assert hits("disputed charges escalation", "keyword") and hits("disputed charges escalation", "hybrid")
    # Vector-only needs real similarity: a close paraphrase clears the threshold, an unrelated query returns nothing
    # (instead of the nearest-but-irrelevant chunk).
    assert hits("Disputed charges must be escalated to the Finance Manager within 2 business days", "vector")
    assert hits("quarterly marketing budget for social media", "vector") == []


# ---- deterministic answer verification (unit) -----------------------------------------------------------------

def _hit(content: str) -> SearchHit:
    return SearchHit(chunk_id=uuid.uuid4(), document_id=uuid.uuid4(), document_title="Policy", doc_type="policy",
                     access_level="general", effective_date=None, version_no=1, section=None, page_number=None,
                     content=content, score=1.0, vector_score=0.9, keyword_score=None, vector_rank=1,
                     keyword_rank=None, flags=[])


def test_fabricated_citations_are_rejected():
    sources = {"S1": _hit("Refunds above 5,000 PHP need Finance Manager approval.")}
    status, cites, checks = answering._verify({
        "status": "answered", "answer": "The Finance Manager approves refunds above 5,000 PHP.",
        "citations": [{"source": "S9", "quote": "anything at all here"},
                      {"source": "S1", "quote": "the CEO approves everything"}]}, sources)
    assert status == "unsupported" and cites == []
    assert [c["reason"] for c in checks["invalid_citations"]] == ["unknown source id", "quote not found in source"]


def test_unsupported_figures_downgrade_the_answer():
    sources = {"S1": _hit("Refunds above 5,000 PHP need Finance Manager approval.")}
    status, cites, checks = answering._verify({
        "status": "answered", "answer": "Refunds above 9,000 PHP need approval.",
        "citations": [{"source": "S1", "quote": "Refunds above 5,000 PHP need Finance Manager approval."}]}, sources)
    assert status == "unsupported" and len(cites) == 1 and checks["unsupported_numbers"] == ["9000"]


def test_quotes_tolerate_whitespace_differences_only():
    sources = {"S1": _hit("Standard supplier payment terms\nare 30 days.")}
    status, cites, _ = answering._verify({
        "status": "answered", "answer": "Payment terms are 30 days.",
        "citations": [{"source": "S1", "quote": "payment terms are 30 days"}]}, sources)
    assert status == "answered" and len(cites) == 1
