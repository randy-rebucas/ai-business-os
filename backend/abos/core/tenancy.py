"""Database-side tenant context for Postgres row-level security (ADR-003).

`require_org_member` is still the authorization boundary; RLS is the second layer that makes a forgotten
`organization_id` filter return nothing instead of another tenant's rows. Each transaction gets two
transaction-local settings, re-applied whenever a Session begins a transaction (they vanish at commit/rollback, so a
pooled connection never carries one request's tenant into the next):

- `app.org_id`       — the active organization; tenant rows of other orgs are invisible and can't be written.
- `app.system_scope` — 'on' only inside `system_scope()`: deliberate cross-tenant work (org deletion, seed, workers
                       that pick jobs across tenants). Never enabled from request input.
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import event
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

ORG_KEY = "abos.tenant_org_id"
SYSTEM_KEY = "abos.system_scope"

_SQL = "SELECT set_config('app.org_id', %s, true), set_config('app.system_scope', %s, true)"


def _apply(session: Session, connection: Connection) -> None:
    org = session.info.get(ORG_KEY)
    system = session.info.get(SYSTEM_KEY, False)
    connection.exec_driver_sql(_SQL, (str(org) if org else "", "on" if system else "off"))


@event.listens_for(Session, "after_begin")
def _after_begin(session: Session, transaction, connection: Connection) -> None:
    if session.info.get(ORG_KEY) or session.info.get(SYSTEM_KEY):
        _apply(session, connection)


def _reapply(db: Session) -> None:
    if db.in_transaction():
        _apply(db, db.connection())


def set_tenant(db: Session, org_id: uuid.UUID | None) -> None:
    """Bind this session to one organization for the rest of its life (current and future transactions)."""
    db.info[ORG_KEY] = org_id
    _reapply(db)


def current_tenant(db: Session) -> uuid.UUID | None:
    return db.info.get(ORG_KEY)


@contextmanager
def system_scope(db: Session) -> Iterator[Session]:
    """Cross-tenant access for platform-level jobs. Keep the block as small as the job allows."""
    previous = db.info.get(SYSTEM_KEY, False)
    db.info[SYSTEM_KEY] = True
    _reapply(db)
    try:
        yield db
    finally:
        db.info[SYSTEM_KEY] = previous
        if db.is_active:
            _reapply(db)
