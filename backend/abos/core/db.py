import uuid
from collections.abc import Iterator
from datetime import datetime

from psycopg import sql
from sqlalchemy import DateTime, ForeignKey, MetaData, create_engine, event, func
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, declared_attr, mapped_column, sessionmaker

from abos.core.config import get_settings

NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


class IdMixin:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TenantMixin:
    """Tenant-owned row. Every table using it needs an RLS policy in its migration (tests/test_rls.py enforces it)."""

    @declared_attr
    def organization_id(cls) -> Mapped[uuid.UUID]:  # noqa: N805
        return mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)


engine = create_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


@event.listens_for(engine, "connect")
def _use_app_role(dbapi_connection, _record) -> None:
    """Run as the non-owner app role so row-level security applies (ADR-003). Committed: a rolled-back SET ROLE
    would silently revert. Migrations use their own connections as the owner."""
    role = get_settings().db_app_role
    if role:
        with dbapi_connection.cursor() as cur:
            cur.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(role)))
        dbapi_connection.commit()


def get_db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


from abos.core import tenancy as _tenancy  # noqa: E402,F401  (registers the RLS tenant-context listener)
