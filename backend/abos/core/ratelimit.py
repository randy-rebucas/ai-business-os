"""Fixed-window rate limits stored in Postgres.

Shared by every API instance. Each hit is one upsert on its own short transaction, so a counted attempt survives
even when the request's own transaction rolls back. Identifiers (IPs, emails, user ids) are stored only as
truncated SHA-256 digests. Coarse flood protection (all requests per IP) belongs to the reverse proxy.
"""

import hashlib
from datetime import UTC, datetime, timedelta

from fastapi import Depends, Request
from sqlalchemy import DateTime, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from abos.core.config import get_settings
from abos.core.db import Base, engine
from abos.core.errors import too_many


class RateLimitBucket(Base):
    __tablename__ = "rate_limit_buckets"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)


_UPSERT = text("""
    INSERT INTO rate_limit_buckets (key, window_start, count) VALUES (:key, :window, 1)
    ON CONFLICT (key, window_start) DO UPDATE SET count = rate_limit_buckets.count + 1
    RETURNING count
""")


def parse(spec: str) -> tuple[int, int]:
    count, seconds = spec.split("/", 1)
    return int(count), int(seconds)


def _digest(identifier: str) -> str:
    return hashlib.sha256(identifier.encode()).hexdigest()[:40]


def hit(limit_name: str, identifier: str | None, *, scope: str) -> None:
    """Count one attempt for (limit, identifier); raise a 429 once the window's allowance is used up."""
    s = get_settings()
    if not s.rate_limits_enabled or not identifier:
        return
    allowed, seconds = parse(getattr(s, f"rl_{limit_name}"))
    now = datetime.now(UTC)
    epoch = int(now.timestamp())
    window = datetime.fromtimestamp(epoch - epoch % seconds, UTC)
    with engine.begin() as conn:
        count = conn.execute(_UPSERT, {"key": f"{limit_name}:{_digest(identifier)}", "window": window}).scalar_one()
    if count > allowed:
        retry = (window + timedelta(seconds=seconds) - now).total_seconds()
        raise too_many("rate_limited", "Too many requests. Wait a moment and try again.", retry, scope,
                       limit=limit_name)


def client_ip(request: Request) -> str | None:
    # uvicorn --proxy-headers resolves X-Forwarded-For from trusted proxies (--forwarded-allow-ips) into client.host.
    return request.client.host if request.client else None


def per_ip(limit_name: str):
    """Dependency: limit by client IP."""

    def _dep(request: Request) -> None:
        hit(limit_name, client_ip(request), scope="ip")

    return Depends(_dep)
