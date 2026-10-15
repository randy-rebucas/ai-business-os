"""The owner path (ADR-033): a database connection as the table owner, used only by housekeeping — organization
deletion and retention purges. The app role can't delete write-once evidence (`tool_executions`), insert-only ledgers
(`payments`, `approvals`, `model_usage`, …) or runs; FK cascades from `organizations` can, when the owner deletes.

Never used by request handlers. In production give only the worker/beat processes ABOS_MAINTENANCE_DATABASE_URL.
"""

from functools import lru_cache

from sqlalchemy import Engine, create_engine

from abos.core.config import get_settings


@lru_cache
def maintenance_engine() -> Engine:
    s = get_settings()
    if s.maintenance_database_url is not None and s.maintenance_database_url.get_secret_value():
        url = s.maintenance_database_url.get_secret_value()
    elif s.env == "production":
        raise RuntimeError("Housekeeping needs ABOS_MAINTENANCE_DATABASE_URL (the table-owner login) in production")
    else:
        url = s.database_url  # dev/test: the login user owns the tables; this engine never does SET ROLE
    return create_engine(url, pool_pre_ping=True, pool_size=2, max_overflow=0)
