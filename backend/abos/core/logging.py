import json
import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
# Correlation fields for background work (job_id, job_kind, org_id, run_id …), added to every log line inside the block.
_context_var: ContextVar[dict[str, Any] | None] = ContextVar("log_context", default=None)


@contextmanager
def log_context(**fields: Any) -> Iterator[None]:
    token = _context_var.set({**(_context_var.get() or {}), **{k: str(v) for k, v in fields.items() if v is not None}})
    try:
        yield
    finally:
        _context_var.reset(token)


def current_log_context() -> dict[str, Any]:
    return dict(_context_var.get() or {})


_base_factory = logging.getLogRecordFactory()


def _record_factory(*args, **kwargs) -> logging.LogRecord:
    # Correlation ids are stamped when the record is created, so handlers that format later (queues, test capture)
    # still see the request/job the line belongs to.
    record = _base_factory(*args, **kwargs)
    record.request_id = request_id_var.get()
    record.log_context = _context_var.get() or {}
    return record


logging.setLogRecordFactory(_record_factory)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
            **getattr(record, "log_context", {}),
        }
        extra = getattr(record, "fields", None)
        if isinstance(extra, dict):
            payload.update(extra)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
