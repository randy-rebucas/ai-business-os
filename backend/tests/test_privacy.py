"""Phase 7 data controls: retention windows, workspace export, scheduled workspace deletion (SPEC §6 'Data retention
and deletion controls'). Deletion is exercised on a workspace that has every kind of protected record — write-once
evidence, insert-only payments and approvals, append-only audit — because those are what the owner path is for."""

import io
import json
import uuid
import zipfile
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import ProgrammingError

from abos.identity.models import EmailOutbox, Organization
from abos.privacy import housekeeping
from abos.privacy.models import OrganizationDeletion
from abos.privacy.service import tenant_tables
from abos.storage import get_storage
from tests.conftest import PASSWORD, indexed, join
from tests.test_agents_api import setup_company
from tests.test_execution import active, d, invoice, start

SOP = "# Credit control\n\nInvoices over 5000 USD need a reminder after 30 days overdue. Refunds need CEO approval.\n"


def populated(actor) -> dict:
    """A workspace with documents, records, an active agent, a run with evidence, a report and notifications."""
    setup_company(actor)
    doc = indexed(actor, "credit-control.md", SOP)
    inv = invoice(actor, "INV-1", due=d(-40), lines=(("Consulting", "2", "2500.00"),))
    invoice(actor, "INV-2", due=d(-5), lines=(("A", "1", "10000.00"), ("B", "1", "2000.00")),  # → escalation
            recorded_total="12500.00", source="import")
    assert actor.post(f"/api/v1/business/invoices/{inv['id']}/payments",
                      json={"amount": "100.00", "received_on": d(0)}).status_code == 201
    inst, _ = active(actor)
    run = start(actor, inst, "review-outstanding-invoices")
    assert run["status"] == "completed", run["status_reason"]
    assert actor.post("/api/v1/reports/generate", json={"agent_id": inst["id"]}).status_code == 201
    assert actor.post("/api/v1/knowledge/ask", json={"question": "When do invoices need a reminder?"}).status_code == 200
    return {"doc": doc, "agent": inst, "run": run}


def _org_rows(db, org_id) -> dict[str, int]:
    out = {}
    for t in tenant_tables():
        n = db.execute(text(f'SELECT count(*) FROM "{t.name}" WHERE organization_id = :id'),  # noqa: S608
                       {"id": org_id}).scalar_one()
        if n:
            out[t.name] = n
    return out


# ---- retention ---------------------------------------------------------------------------------------------------

def test_retention_settings_are_bounded_audited_and_purge_only_past_the_window(owner, rival, db):
    r = owner.get("/api/v1/org/retention").json()
    assert (r["notifications_days"], r["ask_history_days"], r["reports_days"]) == (180, 365, None)
    assert any("Audit log" in k for k in r["kept"])
    assert owner.put("/api/v1/org/retention", json={"notifications_days": 7, "ask_history_days": 365}
                     ).status_code == 422  # below the floor
    assert owner.put("/api/v1/org/retention", json={"notifications_days": 30, "ask_history_days": 30,
                                                    "reports_days": 10}).status_code == 422
    viewer = join(owner, "viewer@acme.example.com", "viewer")
    assert viewer.get("/api/v1/org/retention").status_code == 200
    assert viewer.put("/api/v1/org/retention", json={"notifications_days": 30, "ask_history_days": 30}
                      ).status_code == 403
    r = owner.put("/api/v1/org/retention", json={"notifications_days": 30, "ask_history_days": 30, "reports_days": 90})
    assert r.status_code == 200 and r.json()["reports_days"] == 90
    assert owner.get("/api/v1/audit?action=org.retention_updated").json()[0]["data"]["to"]["notifications_days"] == 30

    for actor in (owner, rival):
        indexed(actor, "faq.md", "# FAQ\n\nThe office opens at 9am.\n")
        assert actor.post("/api/v1/knowledge/ask", json={"question": "When does the office open?"}).status_code == 200
    db.execute(text("UPDATE knowledge_queries SET created_at = now() - interval '40 days'"))
    db.commit()
    result = housekeeping.run()
    # The owner's 30-day window purged their 40-day-old question; the rival keeps the default 365 days.
    assert result["purged"]["knowledge_queries"] == 1
    assert db.execute(text("SELECT count(*) FROM knowledge_queries WHERE organization_id = :o"),
                      {"o": owner.org_id}).scalar_one() == 0
    assert db.execute(text("SELECT count(*) FROM knowledge_queries WHERE organization_id = :o"),
                      {"o": rival.org_id}).scalar_one() == 1
    # Platform housekeeping: rate-limit windows from yesterday go.
    db.execute(text("INSERT INTO rate_limit_buckets (key, window_start, count) "
                    "VALUES ('old', now() - interval '3 days', 1)"))
    db.commit()
    assert housekeeping.run()["purged"]["rate_limit_buckets"] >= 1


# ---- export ------------------------------------------------------------------------------------------------------

def test_export_contains_the_workspace_and_nothing_else(owner, rival, db):
    built = populated(owner)
    indexed(rival, "rival-secret.md", "# Zephyr plan\n\nOur margin target is 41 percent.\n")
    admin = join(owner, "admin@acme.example.com", "admin")
    assert admin.post("/api/v1/org/exports").status_code == 403  # owner only: includes confidential documents
    assert rival.client.post("/api/v1/org/exports", headers={"X-Org-Id": owner.org_id}).status_code == 403
    r = owner.post("/api/v1/org/exports")
    assert r.status_code == 202, r.text
    export = owner.get("/api/v1/org/exports").json()[0]
    assert export["status"] == "ready" and export["size_bytes"] > 0, export
    manifest = export["manifest"]
    assert manifest["format"] == "abos-export/1" and manifest["files"] == 1
    assert manifest["tables"]["tool_executions"] >= 2 and manifest["tables"]["payments"] == 1
    download = owner.get(f"/api/v1/org/exports/{export['id']}/download")
    assert download.status_code == 200 and download.headers["content-type"] == "application/zip"
    z = zipfile.ZipFile(io.BytesIO(download.content))
    names = set(z.namelist())
    assert {"manifest.json", "workspace.json", "members.json", "tables/documents.json",
            "tables/tool_executions.json", "tables/audit_events.json"} <= names
    assert z.read(f"files/{built['doc']['id']}/v1.md").decode() == SOP
    blob = b"".join(z.read(n) for n in names)
    assert b"Zephyr" not in blob and b"41 percent" not in blob and rival.org_id.encode() not in blob
    assert b"password_hash" not in blob and b"argon2" not in blob and b"token_hash" not in blob
    chunks = json.loads(z.read("tables/document_chunks.json"))
    assert chunks and "embedding" not in chunks[0] and "tsv" not in chunks[0]
    assert {m["email"] for m in json.loads(z.read("members.json"))} == {owner.email, "admin@acme.example.com"}
    actions = [e["action"] for e in owner.get("/api/v1/audit?action=org.export").json()]
    assert {"org.export_requested", "org.export_downloaded"} <= set(actions)
    # Expired exports are removed from storage by housekeeping and can't be downloaded any more.
    key = db.scalar(text("SELECT storage_key FROM org_exports"))
    later = datetime.now(UTC) + timedelta(hours=73)
    assert housekeeping.run(later)["exports_expired"] == 1
    assert owner.get("/api/v1/org/exports").json()[0]["status"] == "expired"
    assert owner.get(f"/api/v1/org/exports/{export['id']}/download").status_code == 409
    assert not (get_storage().root / key).exists()


# ---- deletion ----------------------------------------------------------------------------------------------------

def test_workspace_deletion_is_confirmed_scheduled_cancellable_and_complete(owner, rival, db, app_db, client):
    populated(owner)
    indexed(rival, "rival.md", "# Rival\n\nRival handbook.\n")
    admin = join(owner, "admin@acme.example.com", "admin")
    co_owner = join(owner, "owner2@acme.example.com", "owner")
    rival_rows = _org_rows(db, rival.org_id)
    assert admin.post("/api/v1/org/deletion", json={"confirm_name": "Acme Trading", "password": PASSWORD}
                      ).status_code == 403  # org.delete is owner-only
    bad = owner.post("/api/v1/org/deletion", json={"confirm_name": "acme trading", "password": PASSWORD})
    assert bad.json()["error"]["code"] == "confirmation_mismatch"
    bad = owner.post("/api/v1/org/deletion", json={"confirm_name": "Acme Trading", "password": "wrong-password-1"})
    assert bad.json()["error"]["code"] == "invalid_credentials"

    r = owner.post("/api/v1/org/deletion", json={"confirm_name": "Acme Trading", "password": PASSWORD})
    assert r.status_code == 200, r.text
    due = datetime.fromisoformat(r.json()["scheduled_for"])
    assert timedelta(hours=71) < due - datetime.now(UTC) <= timedelta(hours=72)
    assert owner.get("/api/v1/org").json()["deletion_scheduled_at"] is not None  # shown to every member
    mails = db.scalars(select(EmailOutbox.to_email).where(EmailOutbox.subject.like("%scheduled for deletion%"))).all()
    assert sorted(mails) == sorted([owner.email, co_owner.email])  # every owner is told and can cancel
    assert owner.post("/api/v1/org/deletion", json={"confirm_name": "Acme Trading", "password": PASSWORD}
                      ).status_code == 409
    # Cancel → nothing happens even after the original due time; schedule again.
    assert co_owner.delete("/api/v1/org/deletion").json()["scheduled_for"] is None
    assert housekeeping.run(due + timedelta(minutes=1))["deleted_orgs"] == []
    assert owner.post("/api/v1/org/deletion", json={"confirm_name": "Acme Trading", "password": PASSWORD}
                      ).status_code == 200
    assert housekeeping.run()["deleted_orgs"] == []  # still in the grace period

    org_id = uuid.UUID(owner.org_id)
    keys = list(db.scalars(text("SELECT storage_key FROM document_versions WHERE organization_id = :o"),
                           {"o": org_id}))
    before = _org_rows(db, org_id)
    assert {"tool_executions", "payments", "approvals", "audit_events", "model_usage", "document_chunks",
            "daily_reports", "notifications", "knowledge_queries"} <= set(before), before
    db.rollback()

    result = housekeeping.run(datetime.now(UTC) + timedelta(hours=73))
    assert result["deleted_orgs"] == [owner.org_id]
    # Every tenant row is gone, protected ledgers included; audit events stay, detached from the workspace.
    assert _org_rows(db, org_id) == {}
    assert db.get(Organization, org_id) is None
    detached = db.execute(text("SELECT count(*) FROM audit_events WHERE organization_id IS NULL AND target_id = :o "
                               "AND action = 'org.deletion_scheduled'"), {"o": str(org_id)}).scalar_one()
    assert detached == 2
    record = db.scalar(select(OrganizationDeletion).where(OrganizationDeletion.deleted_organization_id == org_id))
    assert record.rows_deleted["tool_executions"] == before["tool_executions"]
    assert record.rows_deleted["audit_events_detached"] == before["audit_events"]
    assert record.files_deleted == len(keys) and record.files_failed == 0
    assert not any((get_storage().root / k).exists() for k in keys)
    # Other workspaces are untouched; people keep their accounts and other workspaces.
    assert _org_rows(db, rival.org_id) == rival_rows
    assert owner.get("/api/v1/org").status_code == 403
    me = owner.client.get("/api/v1/auth/me").json()
    assert [m["organization"]["name"] for m in me["memberships"]] == []
    assert [m["organization"]["name"] for m in admin.client.get("/api/v1/auth/me").json()["memberships"]] == [
        "Member Personal"]
    login = client.post("/api/v1/auth/login", json={"email": owner.email, "password": PASSWORD})
    assert login.status_code == 200
    # The app role can't read deletion records.
    with pytest.raises(ProgrammingError, match="permission denied"):
        app_db.execute(text("SELECT count(*) FROM organization_deletions"))
