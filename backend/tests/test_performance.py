"""Phase 7 performance: list, dashboard and report endpoints run a bounded number of SQL queries — the count must not
grow with the number of agents, runs, invoices or documents (no N+1)."""

import contextlib

from sqlalchemy import event

from abos.core.db import engine
from tests.conftest import indexed
from tests.test_agents_api import setup_company
from tests.test_execution import active, d, invoice, start


@contextlib.contextmanager
def counting():
    box = {"n": 0}

    def _count(*_args, **_kw):
        box["n"] += 1

    event.listen(engine, "before_cursor_execute", _count)
    try:
        yield box
    finally:
        event.remove(engine, "before_cursor_execute", _count)


ENDPOINTS = [
    "/api/v1/dashboard", "/api/v1/agents", "/api/v1/agents/{agent}", "/api/v1/workflows",
    "/api/v1/workflows/{run}", "/api/v1/workflows/tasks", "/api/v1/approvals/pending", "/api/v1/approvals/actions",
    "/api/v1/approvals", "/api/v1/notifications", "/api/v1/reports", "/api/v1/reports/{report}", "/api/v1/usage",
    "/api/v1/business/invoices", "/api/v1/business/receivables", "/api/v1/business/drafts", "/api/v1/documents",
    "/api/v1/simulations/runs", "/api/v1/agents/{agent}/readiness", "/api/v1/tools/executions",
    "/api/v1/audit", "/api/v1/rules", "/api/v1/agents/{agent}/config/versions",
]


def _measure(actor, ids) -> dict[str, int]:
    out = {}
    for path in ENDPOINTS:
        url = path.format(**ids)
        actor.get(url)  # warm caches (session refresh etc.)
        with counting() as c:
            r = actor.get(url)
        assert r.status_code == 200, (url, r.text[:300])
        out[path] = c["n"]
    return out


def _grow(actor, inst, n):
    for i in range(n):
        invoice(actor, f"INV-G{i}-{n}", due=d(-35 - i), lines=(("Work", "1", f"{6000 + i}.00"),))
        start(actor, inst, "review-outstanding-invoices")
        indexed(actor, f"note-{n}-{i}.md", f"# Note {i}\n\nPolicy note number {i}.\n")


def test_query_counts_do_not_grow_with_data(owner):
    setup_company(owner)
    invoice(owner, "INV-1", due=d(-40), lines=(("Consulting", "2", "2500.00"),))
    inst, _ = active(owner)
    run = start(owner, inst, "review-outstanding-invoices")

    def build_report() -> tuple[dict, int]:
        with counting() as c:
            r = owner.post("/api/v1/reports/generate", json={"agent_id": inst["id"]})
        assert r.status_code == 201, r.text
        return r.json(), c["n"]

    report, _ = build_report()
    ids = {"agent": inst["id"], "run": run["id"], "report": report["id"]}
    _, rebuild_small = build_report()
    small = {**_measure(owner, ids), "POST reports/generate": rebuild_small}
    for key in ("executive", "sales", "hr"):
        assert owner.post("/api/v1/agents", json={"definition_keys": [key]}).status_code == 201
    _grow(owner, inst, 4)
    report, rebuild_large = build_report()
    ids["report"] = report["id"]
    large = {**_measure(owner, ids), "POST reports/generate": rebuild_large}
    grew = {k: (small[k], large[k]) for k in small if large[k] > small[k]}
    assert not grew, grew
    assert max(large.values()) <= 30, large  # and every endpoint stays small in absolute terms
