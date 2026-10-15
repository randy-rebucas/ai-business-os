"""Document upload, validation, parsing, chunking and the ingestion pipeline (SPEC §3 step 3)."""

from sqlalchemy import select

from abos.knowledge import chunking, parsing
from abos.knowledge.models import DocumentChunk, JobRun
from tests.conftest import approve, upload
from tests.fixtures import REFUND_POLICY, make_docx, make_pdf, make_xlsx


def test_markdown_upload_runs_full_pipeline_to_review(owner, db):
    doc = upload(owner, "refund-policy.md", REFUND_POLICY, effective_date="2026-01-01")
    assert doc["status"] == "awaiting_review"
    assert doc["doc_type"] == "policy" and doc["chunk_count"] >= 2
    assert doc["summary"] and doc["summary_label"].startswith("Development adapter")
    assert doc["versions"][0]["version_no"] == 1 and doc["versions"][0]["detected_format"] == "md"
    steps = [s["step"] for s in doc["latest_job"]["steps"]]
    assert steps == ["processing", "extracted", "chunked", "embedded", "awaiting_review"]
    assert doc["latest_job"]["status"] == "succeeded"
    chunks = owner.get(f"/api/v1/documents/{doc['id']}/chunks").json()
    sections = {c["section"] for c in chunks}
    assert "Refund Policy > Refunds above the limit" in sections
    # Metadata persisted on the version row; embeddings stored with the configured dimension.
    row = db.scalars(select(DocumentChunk).where(DocumentChunk.document_id == doc["id"])).first()
    assert len(row.embedding) == 1024 and row.organization_id is not None


def test_pdf_pages_are_tracked(owner):
    pdf = make_pdf([["EMPLOYEE HANDBOOK", "", "Working hours are 8:00 to 17:00 on weekdays."],
                    ["Overtime", "Overtime above 10 hours per week needs HR approval."]])
    doc = upload(owner, "handbook.pdf", pdf)
    assert doc["status"] == "awaiting_review", doc["error_message"]
    assert doc["versions"][0]["page_count"] == 2
    pages = {c["page_number"] for c in owner.get(f"/api/v1/documents/{doc['id']}/chunks").json()}
    assert pages == {1, 2}


def test_scanned_pdf_fails_honestly_without_ocr_and_can_be_retried(owner):
    doc = upload(owner, "scan.pdf", make_pdf([None, None]))
    assert doc["status"] == "failed" and doc["error_code"] == "no_text_ocr_unavailable"
    assert "OCR" in doc["error_message"]
    r = owner.post(f"/api/v1/documents/{doc['id']}/retry")
    assert r.status_code == 200 and r.json()["status"] == "failed"  # still no OCR: fails again, no pretending
    approved = owner.post(f"/api/v1/documents/{doc['id']}/review", json={"decision": "approve"})
    assert approved.status_code == 409


def test_mixed_pdf_warns_about_unreadable_pages(owner):
    doc = upload(owner, "mixed.pdf", make_pdf([["Delivery Policy", "Orders ship within 2 business days."], None]))
    assert doc["status"] == "awaiting_review"
    assert any(w["code"] == "ocr_unavailable" for w in doc["warnings"])


def test_docx_headings_and_tables(owner):
    data = make_docx("Sales Playbook", [("Discounts", ["Sales reps may give up to 10% discount without approval."])],
                     table=[["Tier", "Max discount"], ["Gold", "15%"], ["Silver", "8%"]])
    doc = upload(owner, "playbook.docx", data)
    chunks = owner.get(f"/api/v1/documents/{doc['id']}/chunks").json()
    assert any(c["section"] == "Sales Playbook > Discounts" for c in chunks)
    table = next(c for c in chunks if c["kind"] == "table")
    assert "| Gold | 15% |" in table["content"] and "| Tier | Max discount |" in table["content"]


def test_xlsx_sheets_become_tables(owner):
    data = make_xlsx({"Prices": [["SKU", "Price"], ["PX-2041", 1250], ["PX-2042", 1390]]})
    doc = upload(owner, "prices.xlsx", data)
    chunks = owner.get(f"/api/v1/documents/{doc['id']}/chunks").json()
    assert chunks[0]["section"] == "Prices" and "| PX-2041 | 1250 |" in chunks[0]["content"]


def test_upload_validation(owner, monkeypatch):
    def post(name, data):
        return owner.client.post("/api/v1/documents", files={"file": (name, data)}, headers=owner.h())

    r = post("fake.pdf", b"just some text pretending")
    assert r.status_code == 422 and r.json()["error"]["code"] == "type_mismatch"
    assert post("tool.exe", b"MZ\x90\x00").json()["error"]["code"] == "unsupported_type"
    assert post("empty.txt", b"").json()["error"]["code"] == "empty_file"
    assert post("bin.txt", b"\x00\x01\x02binary").json()["error"]["code"] == "unsupported_type"
    assert post("x.docx", b"PK\x03\x04garbage").json()["error"]["code"] == "corrupt_file"
    from abos.core.config import get_settings

    monkeypatch.setattr(get_settings(), "upload_max_bytes", 10)
    r = post("big.txt", b"x" * 50)
    assert r.status_code == 413
    assert owner.get("/api/v1/documents").json() == []  # nothing stored for rejected files


def test_new_version_replaces_index_and_needs_review_again(owner, db):
    doc = upload(owner, "refunds.md", REFUND_POLICY)
    approve(owner, doc)
    r = owner.client.post(f"/api/v1/documents/{doc['id']}/versions",
                          files={"file": ("refunds-v2.md", "# Refund Policy\n\nRefunds up to 7,000 PHP are automatic.")},
                          headers=owner.h())
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "awaiting_review" and [v["version_no"] for v in d["versions"]] == [2, 1]
    contents = " ".join(c["content"] for c in owner.get(f"/api/v1/documents/{doc['id']}/chunks").json())
    assert "7,000" in contents and "5,000" not in contents  # old chunks gone, old file kept as version 1
    old = owner.client.get(f"/api/v1/documents/{doc['id']}/download",
                           params={"version_id": d["versions"][1]["id"]}, headers=owner.h())
    assert old.status_code == 200 and b"5,000" in old.content


def test_download_and_metadata_edit(owner):
    doc = upload(owner, "refunds.md", REFUND_POLICY)
    r = owner.client.get(f"/api/v1/documents/{doc['id']}/download", headers=owner.h())
    assert r.status_code == 200 and r.content == REFUND_POLICY.encode()
    assert "attachment" in r.headers["content-disposition"]
    r = owner.patch(f"/api/v1/documents/{doc['id']}", json={"doc_type": "sop", "title": "Refunds SOP"})
    assert r.json()["doc_type"] == "sop" and r.json()["doc_type_source"] == "reviewer"
    # Reprocessing keeps the reviewer's classification.
    r = owner.post(f"/api/v1/documents/{doc['id']}/reprocess")
    assert r.json()["status"] == "awaiting_review" and r.json()["doc_type"] == "sop"


def test_archive_restore_and_reject(owner):
    doc = upload(owner, "refunds.md", REFUND_POLICY)
    r = owner.post(f"/api/v1/documents/{doc['id']}/review", json={"decision": "reject", "note": "Outdated draft"})
    assert r.json()["status"] == "archived" and r.json()["review_note"] == "Outdated draft"
    r = owner.post(f"/api/v1/documents/{doc['id']}/restore")
    assert r.json()["status"] == "awaiting_review"


def test_failed_job_is_retried_then_succeeds(owner, monkeypatch, db):
    from abos.llm import embeddings

    calls = {"n": 0}
    real = embeddings.embed

    def flaky(s, texts, input_type):
        calls["n"] += 1
        if calls["n"] == 1:
            raise embeddings.EmbeddingError("provider_unreachable", "temporary outage")
        return real(s, texts, input_type)

    monkeypatch.setattr(embeddings, "embed", flaky)
    doc = upload(owner, "refunds.md", REFUND_POLICY)
    assert doc["status"] == "awaiting_review"
    job = db.scalars(select(JobRun).where(JobRun.target_id == doc["id"])).one()
    assert job.attempts == 2 and job.status == "succeeded"


def test_permanent_provider_failure_marks_document_failed(owner, monkeypatch):
    from abos.llm import embeddings

    def down(*_):
        raise embeddings.EmbeddingError("provider_unreachable", "down")

    monkeypatch.setattr(embeddings, "embed", down)
    doc = upload(owner, "refunds.md", REFUND_POLICY)
    assert doc["status"] == "failed" and doc["error_code"] == "provider_unreachable"
    assert doc["latest_job"]["attempts"] == 3 and doc["latest_job"]["status"] == "failed"


def test_member_can_upload_but_not_review(owner):
    from tests.conftest import join

    member = join(owner, "member@acme.example.com", "member")
    doc = upload(member, "refunds.md", REFUND_POLICY)
    r = member.post(f"/api/v1/documents/{doc['id']}/review", json={"decision": "approve"})
    assert r.status_code == 403


# ---- unit level ------------------------------------------------------------------------------------------------

def test_chunker_splits_tables_with_header_and_long_text():
    rows = [["sku", "name"]] + [[f"S-{i:04d}", "x" * 60] for i in range(80)]
    blocks = [parsing.Block("heading", "Catalog", 1), parsing.Block("table", "", rows=rows),
              parsing.Block("heading", "Notes", 1), parsing.Block("text", "Sentence number one. " * 200)]
    chunks = chunking.chunk(blocks)
    tables = [c for c in chunks if c.kind == "table"]
    assert len(tables) > 1 and all(c.content.split("\n\n", 1)[1].startswith("| sku | name |") for c in tables)
    assert all(len(c.content) <= chunking.MAX_CHARS + 200 for c in chunks)
    assert {c.section for c in chunks} == {"Catalog", "Notes"}


def test_heading_detection_is_conservative():
    assert parsing.looks_like_heading("REFUND POLICY") == 1
    assert parsing.looks_like_heading("2.1 Approval limits") == 2
    assert parsing.looks_like_heading("Refunds are processed within 5 days.") == 0
    assert parsing.looks_like_heading("a" * 100) == 0


def test_classifier():
    assert chunking.classify("Price list 2026", "SKU unit price discount per unit price") == "pricing"
    assert chunking.classify("Notes", "random words") == "other"
