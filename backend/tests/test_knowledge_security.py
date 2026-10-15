"""RAG security (SPEC §6): tenant isolation, document access levels, prompt injection, SSRF, ledgers."""

import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import ProgrammingError

from abos.core.tenancy import set_tenant
from abos.knowledge import answer as answering
from abos.knowledge import fetch, parsing, safety
from abos.knowledge.models import DocumentChunk
from abos.knowledge.schemas import SearchHit
from tests.conftest import indexed, join
from tests.fixtures import INJECTED, REFUND_POLICY


def test_other_tenants_cannot_see_or_retrieve_documents(owner, rival):
    doc = indexed(owner, "refunds.md", REFUND_POLICY)
    assert rival.get(f"/api/v1/documents/{doc['id']}").status_code == 404
    assert rival.client.get(f"/api/v1/documents/{doc['id']}/download", headers=rival.h()).status_code == 404
    assert rival.post(f"/api/v1/documents/{doc['id']}/review", json={"decision": "reject"}).status_code == 404
    assert rival.post("/api/v1/knowledge/search", json={"query": "refund Finance Manager"}).json()["hits"] == []
    a = rival.post("/api/v1/knowledge/ask", json={"question": "Who approves refunds above the limit?"}).json()
    assert a["status"] == "insufficient_evidence" and a["sources"] == []


def test_chunks_are_isolated_by_rls_even_without_filters(owner, rival, app_db):
    indexed(owner, "refunds.md", REFUND_POLICY)
    set_tenant(app_db, uuid.UUID(rival.org_id))
    assert app_db.scalars(select(DocumentChunk)).all() == []
    set_tenant(app_db, uuid.UUID(owner.org_id))
    assert app_db.scalars(select(DocumentChunk)).all()


def test_access_levels_are_enforced_in_retrieval(owner):
    secret = indexed(owner, "salaries.md", "# Salary Bands\n\nThe CFO salary band is 400,000 PHP per month.",
                     access_level="confidential")
    member = join(owner, "member@acme.example.com", "member")
    assert member.get(f"/api/v1/documents/{secret['id']}").status_code == 404
    assert all(d["id"] != secret["id"] for d in member.get("/api/v1/documents").json())
    assert member.post("/api/v1/knowledge/search", json={"query": "CFO salary band"}).json()["hits"] == []
    a = member.post("/api/v1/knowledge/ask", json={"question": "What is the CFO salary band?"}).json()
    assert a["status"] == "insufficient_evidence"
    # The owner (confidential access) does get it.
    assert owner.post("/api/v1/knowledge/search", json={"query": "CFO salary band"}).json()["hits"]
    # Members can't classify above their own level.
    r = member.client.post("/api/v1/documents", files={"file": ("x.md", "# X\n\nSecret stuff here.")},
                           data={"access_level": "confidential"}, headers=member.h())
    assert r.status_code == 403


def test_prompt_injection_in_documents_is_flagged_and_never_reaches_the_answer(owner):
    doc = indexed(owner, "suppliers.md", INJECTED)
    assert any(w["code"] == "instruction_like_text" for w in doc["warnings"])
    chunks = owner.get(f"/api/v1/documents/{doc['id']}/chunks").json()
    assert any("instruction_like_text" in c["flags"] for c in chunks)
    a = owner.post("/api/v1/knowledge/ask", json={"question": "What must new suppliers submit?"}).json()
    assert a["status"] == "answered" and "PWNED" not in a["answer"]
    assert "business permit" in a["answer"]


def test_model_never_sees_instruction_like_text():
    hit = SearchHit(chunk_id=uuid.uuid4(), document_id=uuid.uuid4(), document_title="SOP", doc_type="sop",
                    access_level="general", effective_date=None, version_no=1, section=None, page_number=None,
                    content=INJECTED, score=1, vector_score=1, keyword_score=None, vector_rank=1, keyword_rank=None,
                    flags=["instruction_like_text"])
    rendered = answering._render("What must suppliers submit?", {"S1": hit})
    assert "PWNED" not in rendered and "system prompt" not in rendered.lower()
    assert safety.PLACEHOLDER in rendered and "business permit" in rendered


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://example.com/x", "http://example.com:8080/",
                                 "http://user:pw@example.com/", "javascript:alert(1)"])
def test_url_validation_rejects_unsafe_urls(url):
    with pytest.raises(parsing.ParseError):
        fetch.validate_url(url)


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "10.0.0.5", "169.254.169.254", "192.168.1.1", "::1"])
def test_ssrf_guard_rejects_internal_addresses(host):
    with pytest.raises(parsing.ParseError) as exc:
        fetch._public_ip(host, 80)
    assert exc.value.code == "url_forbidden"


def test_url_import_to_internal_address_fails_in_worker(owner):
    r = owner.post("/api/v1/documents/url", json={"url": "http://127.0.0.1/admin"})
    assert r.status_code == 201
    doc = owner.get(f"/api/v1/documents/{r.json()['id']}").json()
    assert doc["status"] == "failed" and doc["error_code"] == "url_forbidden"


def test_url_import_happy_path(owner, monkeypatch):
    html = (b"<html><head><title>Delivery FAQ</title><script>evil()</script></head><body><nav>Menu</nav>"
            b"<h1>Delivery</h1><p>Orders in Metro Manila arrive within 2 business days.</p></body></html>")
    monkeypatch.setattr(fetch, "fetch", lambda url: fetch.Fetched(html, "text/html", url))
    r = owner.post("/api/v1/documents/url", json={"url": "https://example.com/faq"})
    doc = owner.get(f"/api/v1/documents/{r.json()['id']}").json()
    assert doc["status"] == "awaiting_review" and doc["title"] == "Delivery FAQ"
    content = " ".join(c["content"] for c in owner.get(f"/api/v1/documents/{doc['id']}/chunks").json())
    assert "2 business days" in content and "evil" not in content and "Menu" not in content


def test_app_role_cannot_rewrite_answer_or_usage_ledgers(owner, app_db):
    indexed(owner, "refunds.md", REFUND_POLICY)
    owner.post("/api/v1/knowledge/ask", json={"question": "Who approves refunds above the limit?"})
    set_tenant(app_db, uuid.UUID(owner.org_id))
    for table in ("knowledge_queries", "model_usage"):
        with pytest.raises(ProgrammingError, match="permission denied"):
            app_db.execute(text(f"UPDATE {table} SET created_at = now()"))  # noqa: S608
        app_db.rollback()
        set_tenant(app_db, uuid.UUID(owner.org_id))
