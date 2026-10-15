"""Housekeeping (Celery beat hourly; `python -m abos.jobs housekeeping` once): scheduled workspace deletions, then
retention purges. Runs on the owner path (`maintenance.py`) because it must remove rows the app role can't.

Order matters only for files: rows are deleted in one transaction per workspace, then the files they pointed to.
A file that can't be deleted is counted on the deletion record (and logged) — the row that referenced it is gone, so
a retry can't find it; storage-side lifecycle rules are the backstop (docs/OPERATIONS.md).
"""

import json
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import Connection, text

from abos.core.config import get_settings
from abos.core.errors import report_exception
from abos.core.logging import log_context
from abos.privacy import service as privacy  # noqa: F401  (registers the export job handler)
from abos.privacy.maintenance import maintenance_engine
from abos.storage import get_storage

log = logging.getLogger("abos.housekeeping")

# Per-workspace windows (organizations.retention_*). `:now` is a parameter so tests can move time.
_TENANT_PURGES = {
    "notifications": "DELETE FROM notifications n USING organizations o WHERE n.organization_id = o.id "
                     "AND n.created_at < :now - make_interval(days => o.retention_notifications_days)",
    "knowledge_queries": "DELETE FROM knowledge_queries q USING organizations o WHERE q.organization_id = o.id "
                         "AND q.created_at < :now - make_interval(days => o.retention_ask_history_days)",
    "daily_reports": "DELETE FROM daily_reports r USING organizations o WHERE r.organization_id = o.id "
                     "AND o.retention_reports_days IS NOT NULL "
                     "AND r.report_date < (:now - make_interval(days => o.retention_reports_days))::date",
}
# Platform data with fixed windows (settings).
_PLATFORM_PURGES = {
    "job_runs": ("DELETE FROM job_runs WHERE status IN ('succeeded', 'failed') "
                 "AND finished_at < :now - make_interval(days => :days)", "job_runs_retention_days"),
    "user_sessions": ("DELETE FROM user_sessions WHERE coalesce(revoked_at, expires_at) "
                      "< :now - make_interval(days => :days)", "sessions_retention_days"),
    "auth_tokens": ("DELETE FROM auth_tokens WHERE coalesce(used_at, expires_at) < :now - make_interval(days => :days)",
                    "sessions_retention_days"),
    "authentication_events": ("DELETE FROM authentication_events WHERE created_at < :now - make_interval(days => :days)",
                              "auth_events_retention_days"),
    "email_outbox": ("DELETE FROM email_outbox WHERE status IN ('sent', 'failed', 'stored') "
                     "AND created_at < :now - make_interval(days => :days)", "outbox_retention_days"),
}


def run(now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    result: dict = {"deleted_orgs": [], "purged": {}, "exports_expired": 0}
    engine = maintenance_engine()
    with engine.connect() as conn:
        due = [r[0] for r in conn.execute(text("SELECT id FROM organizations WHERE deletion_scheduled_at <= :now"),
                                          {"now": now})]
    for org_id in due:
        try:
            if delete_organization(org_id, now):
                result["deleted_orgs"].append(str(org_id))
        except Exception as exc:  # noqa: BLE001 — one failing workspace must not stop the others
            report_exception(exc, {"org_id": str(org_id)}, where="housekeeping")
    result["exports_expired"] = _expire_exports(now)
    with engine.begin() as conn:
        for name, sql in _TENANT_PURGES.items():
            result["purged"][name] = conn.execute(text(sql), {"now": now}).rowcount
        s = get_settings()
        for name, (sql, setting) in _PLATFORM_PURGES.items():
            result["purged"][name] = conn.execute(text(sql), {"now": now, "days": getattr(s, setting)}).rowcount
        result["purged"]["rate_limit_buckets"] = conn.execute(
            text("DELETE FROM rate_limit_buckets WHERE window_start < :now - interval '1 day'"), {"now": now}).rowcount
    log.info("housekeeping", extra={"fields": {"deleted_orgs": len(result["deleted_orgs"]), **result["purged"]}})
    return result


def _counts(conn: Connection, org_id: uuid.UUID) -> dict[str, int]:
    counts = {}
    for table in privacy.tenant_tables():
        n = conn.execute(text(f'SELECT count(*) FROM "{table.name}" WHERE organization_id = :id'),  # noqa: S608
                         {"id": org_id}).scalar_one()
        if n:
            counts[table.name] = n
    return counts


def delete_organization(org_id: uuid.UUID, now: datetime) -> bool:
    """Delete one workspace whose grace period has passed: every tenant row (FK cascades from `organizations`),
    then its files. Audit events stay as the platform's security record with the workspace link removed
    (the append-only trigger allows exactly that). Returns False if it wasn't due (cancelled meanwhile)."""
    engine = maintenance_engine()
    with log_context(org_id=org_id), engine.begin() as conn:
        org = conn.execute(text("SELECT id, deletion_scheduled_at, deletion_requested_by_id, "
                                "(SELECT min(created_at) FROM audit_events a WHERE a.organization_id = o.id "
                                " AND a.action = 'org.deletion_scheduled') AS requested_at "
                                "FROM organizations o WHERE id = :id AND deletion_scheduled_at <= :now "
                                "FOR UPDATE SKIP LOCKED"), {"id": org_id, "now": now}).mappings().first()
        if org is None:
            return False
        keys = [r[0] for r in conn.execute(text(
            "SELECT storage_key FROM document_versions WHERE organization_id = :id UNION "
            "SELECT storage_key FROM org_exports WHERE organization_id = :id AND storage_key IS NOT NULL"),
            {"id": org_id})]
        counts = _counts(conn, org_id)
        counts["audit_events_detached"] = counts.pop("audit_events", 0)
        conn.execute(text("DELETE FROM organizations WHERE id = :id"), {"id": org_id})
        record_id = uuid.uuid4()
        conn.execute(text("INSERT INTO organization_deletions (id, deleted_organization_id, requested_by_id, requested_at, "
                          "scheduled_for, completed_at, rows_deleted, files_deleted, files_failed) VALUES "
                          "(:rid, :id, :by, :req, :sched, now(), CAST(:rows AS jsonb), 0, 0)"),
                     {"rid": record_id, "id": org_id, "by": org["deletion_requested_by_id"],
                      "req": org["requested_at"], "sched": org["deletion_scheduled_at"], "rows": json.dumps(counts)})
    deleted, failed = _delete_files(keys)
    with engine.begin() as conn:
        conn.execute(text("UPDATE organization_deletions SET files_deleted = :d, files_failed = :f WHERE id = :rid"),
                     {"d": deleted, "f": failed, "rid": record_id})
    log.info("organization_deleted", extra={"fields": {"org_id": str(org_id), "rows": sum(counts.values()),
                                                       "files_deleted": deleted, "files_failed": failed}})
    return True


def _delete_files(keys: list[str]) -> tuple[int, int]:
    storage, deleted, failed = get_storage(), 0, 0
    for key in keys:
        try:
            storage.delete(key)
            deleted += 1
        except Exception as exc:  # noqa: BLE001 — counted and reported; see module docstring
            failed += 1
            report_exception(exc, {"storage_key_prefix": key.split("/", 1)[0]}, where="housekeeping")
    return deleted, failed


def _expire_exports(now: datetime) -> int:
    engine = maintenance_engine()
    with engine.begin() as conn:
        rows = conn.execute(text("SELECT id, storage_key FROM org_exports WHERE status = 'ready' "
                                 "AND expires_at <= :now FOR UPDATE SKIP LOCKED"), {"now": now}).all()
        if rows:
            conn.execute(text("UPDATE org_exports SET status = 'expired', storage_key = NULL, updated_at = now() "
                              "WHERE id = ANY(:ids)"), {"ids": [r[0] for r in rows]})
    _delete_files([r[1] for r in rows if r[1]])
    return len(rows)
