import os
import re
import tempfile

os.environ["ABOS_ENV"] = "test"
# Jobs run inline after commit; files go to a throwaway dir; AI adapters are the labelled dev ones — whatever a
# developer has in backend/.env (env vars override the file).
os.environ["ABOS_JOBS_EAGER"] = "true"
os.environ["ABOS_STORAGE_BACKEND"] = "local"
os.environ["ABOS_STORAGE_DIR"] = tempfile.mkdtemp(prefix="abos-test-storage-")
os.environ["ABOS_LLM_PROVIDER"] = "dev"
os.environ["ABOS_ANTHROPIC_API_KEY"] = ""
os.environ["ABOS_EMBEDDING_PROVIDER"] = "hash"
os.environ["ABOS_RATE_LIMITS_ENABLED"] = "true"
os.environ["ABOS_DATABASE_URL"] = os.environ.get(
    "ABOS_TEST_DATABASE_URL", "postgresql+psycopg://abos:abos_dev_password@127.0.0.1:55470/abos_test"
)
os.environ["ABOS_LOG_LEVEL"] = "WARNING"
os.environ["ABOS_MAILER"] = "dev_outbox"

import pytest  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, select, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from abos.core.db import Base, SessionLocal  # noqa: E402
from abos.identity.models import EmailOutbox  # noqa: E402
from abos.main import app  # noqa: E402
from alembic import command  # noqa: E402

PASSWORD = "correct-horse-battery"

# The app engine runs as the RLS-bound `abos_app` role (ADR-003). Tests inspect and clean the database through the
# owner login instead — the test's privileged view. DB triggers still apply to it.
owner_engine = create_engine(os.environ["ABOS_DATABASE_URL"])
OwnerSession = sessionmaker(bind=owner_engine, expire_on_commit=False)


@pytest.fixture(scope="session", autouse=True)
def _migrate():
    here = os.path.dirname(__file__)
    cfg = Config(os.path.join(here, "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(here, "..", "alembic"))
    cfg.set_main_option("sqlalchemy.url", os.environ["ABOS_DATABASE_URL"])
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield


SEEDED_BY_MIGRATIONS = {"agent_definitions"}  # platform catalog: kept between tests


@pytest.fixture(autouse=True)
def _clean():
    yield
    # TRUNCATE is slow per table on Docker Desktop volumes, so only touch tables that have rows.
    names = [t.name for t in Base.metadata.sorted_tables if t.name not in SEEDED_BY_MIGRATIONS]
    probe = " UNION ALL ".join(f"SELECT '{n}' WHERE EXISTS (SELECT 1 FROM \"{n}\")" for n in names)  # noqa: S608
    with owner_engine.begin() as conn:
        dirty = [r[0] for r in conn.execute(text(probe))]
        if dirty:
            # session_replication_role=replica skips user triggers (append-only audit) and FK checks, so order doesn't
            # matter. DELETE, not TRUNCATE: TRUNCATE fsyncs new relation files, which costs seconds per test on Docker
            # Desktop volumes; the tables are tiny. (All keys are UUIDs — no sequences to reset.)
            conn.execute(text("SET LOCAL session_replication_role = replica"))
            for n in dirty:
                conn.execute(text(f'DELETE FROM "{n}"'))  # noqa: S608 — table names come from the ORM metadata


@pytest.fixture
def db():
    """Owner-level session for assertions about stored data (not subject to RLS)."""
    with OwnerSession() as session:
        yield session


@pytest.fixture
def app_db():
    """A session exactly like the app's: `abos_app` role, RLS applies."""
    with SessionLocal() as session:
        yield session


def new_client() -> TestClient:
    return TestClient(app, headers={"X-Requested-With": "abos"})


@pytest.fixture
def client() -> TestClient:
    return new_client()


class Actor:
    """A signed-in user with its own cookie jar and active org."""

    def __init__(self, client: TestClient, me: dict):
        self.client = client
        self.me = me
        self.user_id = me["user"]["id"]
        self.email = me["user"]["email"]
        self.org_id = me["memberships"][0]["organization"]["id"] if me["memberships"] else None

    def h(self, org_id: str | None = None) -> dict:
        return {"X-Org-Id": org_id or self.org_id}

    def get(self, url, org=True, **kw):
        return self.client.get(url, headers=self.h() if org else None, **kw)

    def post(self, url, json=None, org=True, **kw):
        return self.client.post(url, json=json, headers=self.h() if org else None, **kw)

    def patch(self, url, json=None, org=True, **kw):
        return self.client.patch(url, json=json, headers=self.h() if org else None, **kw)

    def put(self, url, json=None, org=True, **kw):
        return self.client.put(url, json=json, headers=self.h() if org else None, **kw)

    def delete(self, url, org=True, **kw):
        return self.client.delete(url, headers=self.h() if org else None, **kw)


def register(email: str, org: str = "Acme Trading", name: str = "Test User", job_title: str | None = "CEO") -> Actor:
    c = new_client()
    body = {"email": email, "password": PASSWORD, "full_name": name, "organization_name": org}
    if job_title:
        body["job_title"] = job_title
    r = c.post("/api/v1/auth/register", json=body)
    assert r.status_code == 201, r.text
    return Actor(c, r.json())


def last_email_token(email: str, path: str) -> str:
    with OwnerSession() as s:
        msg = s.scalars(select(EmailOutbox).where(EmailOutbox.to_email == email)
                        .order_by(EmailOutbox.created_at.desc())).first()
    m = re.search(rf"{path}\?token=([\w-]+)", msg.body)
    assert m, msg.body
    return m.group(1)


def join(owner: Actor, email: str, role: str, name: str = "Member") -> Actor:
    """Register a user (with their own org) and add them to owner's org with `role`; switch them to it."""
    member = register(email, org=f"{name} Personal", name=name, job_title=None)
    r = owner.post("/api/v1/org/members", json={"email": email, "role": role})
    assert r.status_code == 201, r.text
    member.org_id = owner.org_id
    return member


def upload(actor: Actor, name: str, content: bytes | str, **form) -> dict:
    data = content.encode() if isinstance(content, str) else content
    r = actor.client.post("/api/v1/documents", files={"file": (name, data)},
                          data={k: str(v) for k, v in form.items()}, headers=actor.h())
    assert r.status_code == 201, r.text
    return actor.get(f"/api/v1/documents/{r.json()['id']}").json()


def approve(actor: Actor, doc: dict, **meta) -> dict:
    r = actor.post(f"/api/v1/documents/{doc['id']}/review", json={"decision": "approve", **meta})
    assert r.status_code == 200, r.text
    return r.json()


def indexed(actor: Actor, name: str, content: bytes | str, **form) -> dict:
    doc = upload(actor, name, content, **form)
    assert doc["status"] == "awaiting_review", doc
    return approve(actor, doc)


@pytest.fixture
def owner() -> Actor:
    return register("ceo@acme.example.com")


@pytest.fixture
def rival() -> Actor:
    return register("ceo@rival.example.com", org="Rival Corp")
