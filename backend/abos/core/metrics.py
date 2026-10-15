"""Prometheus metrics (text exposition format 0.0.4), without a client library (ADR-032).

Two sources:
- in-process counters/histograms for this API process (requests, latency, unhandled errors);
- gauges computed from the database at scrape time (jobs, workflow runs, tool executions, deliveries, documents).
  Background work runs in other processes (Celery worker, beat), so counting it here from the durable rows is the
  only way every replica reports the same, correct numbers. They are platform-wide totals — no tenant labels.

Scraped at GET /api/metrics with a bearer token (ABOS_METRICS_TOKEN); the endpoint is off without one.
"""

import threading
import time
from collections import defaultdict
from collections.abc import Iterable

from sqlalchemy import text

_lock = threading.Lock()
LATENCY_BUCKETS = (0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

_requests: dict[tuple[str, str, str], int] = defaultdict(int)
_latency_buckets: dict[tuple[str, str], list[int]] = {}
_latency_sum: dict[tuple[str, str], float] = defaultdict(float)
_latency_count: dict[tuple[str, str], int] = defaultdict(int)
_errors: dict[str, int] = defaultdict(int)
_started = time.time()


def observe_request(method: str, route: str, status: int, seconds: float) -> None:
    key = (method, route)
    with _lock:
        _requests[(method, route, str(status))] += 1
        buckets = _latency_buckets.setdefault(key, [0] * len(LATENCY_BUCKETS))
        for i, bound in enumerate(LATENCY_BUCKETS):
            if seconds <= bound:
                buckets[i] += 1
        _latency_sum[key] += seconds
        _latency_count[key] += 1


def count_error(where: str) -> None:
    with _lock:
        _errors[where] += 1


def _esc(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _labels(**labels: str) -> str:
    return "{" + ",".join(f'{k}="{_esc(str(v))}"' for k, v in labels.items()) + "}" if labels else ""


def _family(name: str, kind: str, help_text: str, samples: Iterable[str]) -> list[str]:
    return [f"# HELP {name} {help_text}", f"# TYPE {name} {kind}", *samples]


def _process_metrics() -> list[str]:
    with _lock:
        requests = dict(_requests)
        buckets = {k: list(v) for k, v in _latency_buckets.items()}
        sums, counts, errors = dict(_latency_sum), dict(_latency_count), dict(_errors)
    out = _family("abos_http_requests_total", "counter", "HTTP requests by method, route template and status.",
                  (f"abos_http_requests_total{_labels(method=m, route=r, status=s)} {n}"
                   for (m, r, s), n in sorted(requests.items())))
    latency: list[str] = []
    for (m, r), counts_by_bucket in sorted(buckets.items()):
        for bound, n in zip(LATENCY_BUCKETS, counts_by_bucket, strict=True):
            latency.append(f"abos_http_request_duration_seconds_bucket{_labels(method=m, route=r, le=str(bound))} {n}")
        latency.append(f"abos_http_request_duration_seconds_bucket{_labels(method=m, route=r, le='+Inf')} "
                       f"{counts[(m, r)]}")
        latency.append(f"abos_http_request_duration_seconds_sum{_labels(method=m, route=r)} {sums[(m, r)]:.6f}")
        latency.append(f"abos_http_request_duration_seconds_count{_labels(method=m, route=r)} {counts[(m, r)]}")
    out += _family("abos_http_request_duration_seconds", "histogram", "API request latency.", latency)
    out += _family("abos_unhandled_errors_total", "counter", "Unhandled exceptions reported by this process.",
                   (f"abos_unhandled_errors_total{_labels(where=w)} {n}" for w, n in sorted(errors.items())))
    out += _family("abos_process_start_time_seconds", "gauge", "Start time of this API process.",
                   [f"abos_process_start_time_seconds {_started:.0f}"])
    return out


# Each query returns (label values…, value). Windows are fixed (24 h) so the numbers are comparable between scrapes.
_DB_GAUGES: list[tuple[str, str, tuple[str, ...], str]] = [
    ("abos_jobs", "Background jobs by kind and status (queued/running now; succeeded/failed in the last 24 h).",
     ("kind", "status"),
     "SELECT kind, status, count(*) FROM job_runs WHERE status IN ('queued', 'running') "
     "OR finished_at > now() - interval '24 hours' GROUP BY kind, status"),
    ("abos_jobs_oldest_queued_seconds", "Age of the oldest queued job (queue lag; 0 when the queue is empty).", (),
     "SELECT coalesce(extract(epoch FROM now() - min(created_at)), 0) FROM job_runs WHERE status = 'queued'"),
    ("abos_workflow_runs_24h", "Agent workflow runs created in the last 24 h by status.", ("status",),
     "SELECT status, count(*) FROM workflow_runs WHERE created_at > now() - interval '24 hours' GROUP BY status"),
    ("abos_tool_executions_24h", "Tool executions in the last 24 h by status.", ("status",),
     "SELECT status, count(*) FROM tool_executions WHERE created_at > now() - interval '24 hours' GROUP BY status"),
    ("abos_notification_deliveries_24h", "Notification deliveries created in the last 24 h by channel and status.",
     ("channel", "status"),
     "SELECT channel, status, count(*) FROM notification_deliveries WHERE created_at > now() - interval '24 hours' "
     "GROUP BY channel, status"),
    ("abos_documents", "Documents by processing status.", ("status",),
     "SELECT status, count(*) FROM documents GROUP BY status"),
    ("abos_action_requests_pending", "Agent actions waiting for a human decision.", (),
     "SELECT count(*) FROM action_requests WHERE status = 'pending'"),
]

_cache: tuple[float, list[str]] | None = None
CACHE_SECONDS = 15.0


def _db_metrics() -> list[str]:
    global _cache
    now = time.monotonic()
    if _cache and now - _cache[0] < CACHE_SECONDS:
        return _cache[1]
    from abos.core.db import SessionLocal  # noqa: PLC0415 — keep this module import-light
    from abos.core.tenancy import system_scope  # noqa: PLC0415

    out: list[str] = []
    with SessionLocal() as db, system_scope(db):  # platform-wide totals; no tenant data leaves as labels
        for name, help_text, labels, sql in _DB_GAUGES:
            rows = db.execute(text(sql)).all()
            out += _family(name, "gauge", help_text,
                           (f"{name}{_labels(**dict(zip(labels, row[:-1], strict=True)))} {float(row[-1]):g}"
                            for row in rows))
        db.rollback()
    _cache = (now, out)
    return out


def render() -> str:
    lines = _process_metrics()
    try:
        lines += _db_metrics()
        up = 1
    except Exception:  # noqa: BLE001 — a scrape must still answer when the database is down
        up = 0
    lines += _family("abos_database_up", "gauge", "1 if the metrics queries reached the database.",
                     [f"abos_database_up {up}"])
    return "\n".join(lines) + "\n"


def reset_for_tests() -> None:
    global _cache
    with _lock:
        _requests.clear()
        _latency_buckets.clear()
        _latency_sum.clear()
        _latency_count.clear()
        _errors.clear()
    _cache = None
