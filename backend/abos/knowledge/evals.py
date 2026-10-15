"""RAG evaluation (SPEC §3 RAG evaluation, §9 RAG quality tests).

Each case runs the real retrieval + answer path with the case's access levels and is graded by deterministic
checks — no LLM judge. Security checks (forbidden documents retrieved, forbidden phrases in the answer) fail a
case regardless of everything else. Runs store their configuration so different retrieval settings can be compared.
"""

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from abos.audit import service as audit
from abos.core.config import get_settings
from abos.core.errors import AppError
from abos.identity.deps import OrgContext
from abos.knowledge import answer as answering
from abos.knowledge import retrieval
from abos.knowledge.documents import allowed_levels
from abos.knowledge.models import RagEvalCase, RagEvalResult, RagEvalRun
from abos.llm import gateway

SECURITY_CHECKS = ("forbidden_sources_absent", "forbidden_phrases_absent")


def _check(passed: bool, detail: str = "") -> dict:
    return {"passed": passed, "detail": detail}


def run_case(db: Session, caller: gateway.Caller, case: RagEvalCase, *, mode: str, top_k: int) -> dict:
    found = retrieval.search(db, caller, case.question, levels=case.access_levels, top_k=top_k, mode=mode)
    ans = answering.answer(db, caller, case.question, found, persist=False)
    retrieved_docs = list(dict.fromkeys(str(h.document_id) for h in found.hits))
    expected, forbidden = set(case.expected_document_ids), set(case.forbidden_document_ids)

    rank = next((i for i, d in enumerate(retrieved_docs, 1) if d in expected), None)
    rr = 1 / rank if rank else 0.0
    precision = (sum(1 for h in found.hits if str(h.document_id) in expected) / len(found.hits)) \
        if expected and found.hits else 0.0

    text = ans.answer.lower()
    checks: dict[str, dict] = {
        "status": _check(ans.status == case.expected_status, f"expected {case.expected_status}, got {ans.status}"),
        "citations_valid": _check(not ans.checks["invalid_citations"],
                                  f"{len(ans.checks['invalid_citations'])} invalid citation(s)"),
        "no_unsupported_claims": _check(not ans.checks["unsupported_numbers"],
                                        ", ".join(ans.checks["unsupported_numbers"])),
        "forbidden_sources_absent": _check(not (forbidden & set(retrieved_docs)),
                                           "a forbidden document was retrieved" if forbidden & set(retrieved_docs)
                                           else ""),
        "forbidden_phrases_absent": _check(not [p for p in case.forbidden_phrases if p.lower() in text],
                                           ", ".join(p for p in case.forbidden_phrases if p.lower() in text)),
    }
    if case.expected_answer_contains:
        missing = [p for p in case.expected_answer_contains if p.lower() not in text]
        checks["answer_contains"] = _check(not missing, "missing: " + ", ".join(missing) if missing else "")
    if expected:
        checks["expected_source_retrieved"] = _check(rank is not None, f"rank {rank}" if rank else "not retrieved")
        if case.expected_status in ("answered", "conflicting"):
            cited = {str(c.document_id) for c in ans.citations}
            checks["expected_source_cited"] = _check(bool(cited & expected), "")
    failures = [f"{name}: {c['detail']}".rstrip(": ") for name, c in checks.items() if not c["passed"]]
    return {"answer": ans, "retrieved_docs": retrieved_docs, "rr": rr, "precision": precision, "checks": checks,
            "failures": failures, "passed": not failures}


def run(db: Session, ctx: OrgContext, *, mode: str, top_k: int) -> RagEvalRun:
    cases = list(db.scalars(select(RagEvalCase).where(RagEvalCase.organization_id == ctx.org_id)
                            .order_by(RagEvalCase.created_at)))
    if not cases:
        raise AppError(409, "no_cases", "Add at least one evaluation case first")
    mine = set(allowed_levels(ctx))
    for case in cases:  # an evaluator can't use a case to read above their own access level
        if not set(case.access_levels) <= mine:
            raise AppError(403, "forbidden", "Some cases use access levels above yours")
    s = get_settings()
    caller = gateway.Caller(org_id=ctx.org_id, user_id=ctx.user.id)
    run_row = RagEvalRun(id=uuid.uuid4(), organization_id=ctx.org_id, created_by_id=ctx.user.id,
                         config={"mode": mode, "top_k": top_k, "llm_provider": s.llm_provider,
                                 "embedding_provider": s.embedding_provider, "embedding_model": s.embedding_model},
                         case_count=len(cases))
    db.add(run_row)
    results, by_cat = [], {}
    for case in cases:
        r = run_case(db, caller, case, mode=mode, top_k=top_k)
        results.append(r)
        cat = by_cat.setdefault(case.category, {"cases": 0, "passed": 0})
        cat["cases"] += 1
        cat["passed"] += int(r["passed"])
        db.add(RagEvalResult(organization_id=ctx.org_id, run_id=run_row.id, case_id=case.id, question=case.question,
                             category=case.category, passed=r["passed"], status=r["answer"].status,
                             answer=r["answer"].answer, retrieved_document_ids=r["retrieved_docs"],
                             reciprocal_rank=Decimal(str(round(r["rr"], 4))),
                             precision=Decimal(str(round(r["precision"], 4))), checks=r["checks"],
                             failure_reasons=r["failures"]))
    with_expected = [r for r, c in zip(results, cases, strict=True) if c.expected_document_ids]
    run_row.passed_count = sum(r["passed"] for r in results)
    run_row.metrics = {
        "pass_rate": round(run_row.passed_count / len(cases), 4),
        "mrr": round(sum(r["rr"] for r in with_expected) / len(with_expected), 4) if with_expected else None,
        "hit_rate": round(sum(r["rr"] > 0 for r in with_expected) / len(with_expected), 4) if with_expected else None,
        "precision": round(sum(r["precision"] for r in with_expected) / len(with_expected), 4) if with_expected else None,
        "citation_validity": round(sum(r["checks"]["citations_valid"]["passed"] for r in results) / len(results), 4),
        "security_failures": sum(any(not r["checks"][k]["passed"] for k in SECURITY_CHECKS) for r in results),
        "by_category": by_cat,
    }
    audit.record(db, "knowledge.eval_run", actor_id=ctx.user.id, org_id=ctx.org_id, target_type="rag_eval_run",
                 target_id=run_row.id, data={"config": run_row.config, "pass_rate": run_row.metrics["pass_rate"]},
                 ip=ctx.meta.ip)
    db.commit()
    db.refresh(run_row)
    return run_row
