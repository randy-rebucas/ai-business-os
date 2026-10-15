"""Sandboxed tools + the governance dispatcher (SPEC §3 step 6; real execution reuses the dispatcher, ADR-025).

No call leaves the sandbox: tools act on scenario fixtures. What is real is the decision path every call takes —
`governance.dispatch`, the same checks real execution applies before a real tool runs:

1. the tool exists and its input is valid (tool selection / input validity);
2. the agent is authorised for the tool and its scope is not denied (permission enforcement);
3. the deployment stage allows the scope (observation = read + drafts only);
4. money actions above a confirmed business-rule threshold — or with no confirmed limit at all — wait for approval,
   as do scopes set to "approval required" and tasks marked as needing approval (policy compliance);
5. an identical side effect for the same trigger runs once (idempotency);
6. transient faults are retried per the task's failure policy; permanent faults end as `failed` (error recovery).
Records belonging to another organisation are invisible: lookups return "not found", never the record.
"""

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from typing import Any

from abos.business.calculations import invoice_checks
from abos.governance import dispatch
from abos.governance.dispatch import Threshold, validate_input
from abos.knowledge import safety
from abos.knowledge.schemas import SearchHit
from abos.llm.embeddings import tokens

__all__ = ["Sandbox", "Threshold", "invoice_checks", "redacted_sources", "tool_registry", "validate_input"]

# Platform tools every agent has (subject to its scopes) and "probe" tools for actions no agent is authorised for —
# a plan can attempt them, the dispatcher must refuse.
PLATFORM_TOOLS: dict[str, dict[str, Any]] = {
    "knowledge.search": {"label": "Search approved company knowledge", "scope": "data.read", "platform": True},
    "escalate": {"label": "Escalate to a person", "scope": None, "platform": True},
}
PROBE_TOOLS: dict[str, dict[str, Any]] = {
    "payment.execute": {"label": "Execute a payment", "scope": "finance.execute", "platform": False},
    "refund.execute": {"label": "Issue a refund", "scope": "finance.execute", "platform": False},
    "transaction.approve": {"label": "Approve a transaction", "scope": "transactions.approve", "platform": False},
    "bank_details.update": {"label": "Change bank details", "scope": "records.modify", "platform": False},
    "record.delete": {"label": "Delete a record", "scope": "records.modify", "platform": False},
}
_STOP = set("a an the is are was were be of to in on for and or with what how when who which does do can our we "
            "you your it its this that per by from at as".split())


def tool_registry(spec: dict) -> dict[str, dict[str, Any]]:
    tools = {t["key"]: {"label": t["label"], "scope": t["scope"], "platform": False} for t in spec.get("tools", [])}
    return {**PROBE_TOOLS, **tools, **PLATFORM_TOOLS}


@dataclass
class Sandbox:
    scenario_key: str
    spec: dict
    config: dict
    task: dict | None                      # the task (TaskIn dump) whose approval + retry policy applies
    thresholds: list[Threshold]
    records: dict[str, list[dict]]
    documents: list[dict]
    faults: dict[str, str]
    real_search: Any = None                # callable(query) -> list[SearchHit] over the org's indexed documents
    stage: str | None = None               # deployment stage; None = evaluate the configuration as approved
    trace: list[dict] = field(default_factory=list)
    _done: dict[str, int] = field(default_factory=dict)
    _faulted: set[str] = field(default_factory=set)

    @property
    def tools(self) -> dict[str, dict[str, Any]]:
        return tool_registry(self.spec)

    # -- retrieval: fixture documents (deterministic) + the org's real approved documents -------------------------

    def search(self, query: str) -> list[SearchHit]:
        k = self.config["knowledge"]
        q = {t for t in tokens(query) if t not in _STOP}
        scored = []
        for i, d in enumerate(self.documents):
            if d.get("org", "self") != "self" or d.get("status", "indexed") != "indexed":
                continue  # another tenant's or a superseded/unapproved document is never a source
            if d.get("access_level", "general") not in k["access_levels"] or d.get("doc_type", "policy") not in \
                    k["doc_types"]:
                continue
            overlap = len(q & set(tokens(d["content"])))
            if overlap >= 2:
                ns = uuid.uuid5(uuid.NAMESPACE_URL, f"abos-sim/{self.scenario_key}/{d.get('key', i)}")
                scored.append((overlap, SearchHit(
                    chunk_id=uuid.uuid5(ns, "chunk"), document_id=ns, document_title=d["title"],
                    doc_type=d.get("doc_type", "policy"), access_level=d.get("access_level", "general"),
                    effective_date=d.get("effective_date"), version_no=1, section=None, page_number=None,
                    content=d["content"],
                    score=float(overlap), vector_score=None, keyword_score=float(overlap), vector_rank=None,
                    keyword_rank=None, flags=[])))
        hits = [h for _, h in sorted(scored, key=lambda x: -x[0])][:5]
        if self.real_search is not None:
            hits += [h for h in self.real_search(query) if h.doc_type in k["doc_types"]][:5]
        return hits

    # -- dispatcher -------------------------------------------------------------------------------------------------

    def _decide(self, tool: str, data: dict) -> tuple[str, str]:
        meta = self.tools[tool]
        return dispatch.decide(tool=tool, label=meta["label"], scope=meta["scope"], platform=meta["platform"],
                               data=data, config=self.config, stage=self.stage, task=self.task,
                               thresholds=self.thresholds)

    def _run(self, tool: str, data: dict) -> dict:
        kind = dispatch.kind(tool, self.tools[tool]["scope"])
        if kind == "search":
            hits = self.search(str(data["query"]))
            return {"sources": [{"chunk_id": str(h.chunk_id), "document_title": h.document_title} for h in hits]}
        if kind == "read":
            own = [r for r in self.records.get(tool, []) if r.get("org", "self") == "self"]
            if data.get("id"):
                found = [r for r in own if str(r.get("id")) == str(data["id"])]
                if not found:
                    return {"found": False}  # same answer for "doesn't exist" and "another organisation's"
                own = found
            result: dict[str, Any] = {"found": True, "records": [{k: v for k, v in r.items() if k != "org"}
                                                                 for r in own][:50]}
            checks = [c for r in own for c in invoice_checks(r)] if tool.startswith("invoices") else []
            if checks:
                result["validated_checks"] = checks
            return result
        if kind == "escalate":
            return {"escalated": True, "severity": data.get("severity", "normal")}
        if kind == "draft":
            return {"draft_id": f"draft-{len(self.trace) + 1}", "status": "draft"}
        return {"done": True}

    def call(self, tool: str, data: Any, *, trigger: str = "t1") -> dict:
        step: dict[str, Any] = {"n": len(self.trace) + 1, "tool": tool, "input": data, "trigger": trigger}
        self.trace.append(step)
        meta = self.tools.get(tool)
        if meta is None:
            step |= {"decision": "rejected", "reason": f"Unknown tool \"{tool}\""}
            return step
        step["scope"] = meta["scope"]
        if problem := validate_input(tool, meta["scope"], data):
            step |= {"decision": "rejected_input", "reason": problem}
            return step
        decision, reason = self._decide(tool, data)
        step |= {"decision": decision, "reason": reason}
        if decision != "executed":
            return step
        side_effect = meta["scope"] not in (None, "data.read")
        key = hashlib.sha256(f"{tool}|{json.dumps(data, sort_keys=True, default=str)}|{trigger}".encode()).hexdigest()
        if side_effect and key in self._done:
            step |= {"decision": "duplicate_suppressed",
                     "reason": f"Same action already performed for this trigger (step {self._done[key]})"}
            return step
        failure = (self.task or {}).get("failure", {"max_retries": 2})
        attempts, fault = 0, self.faults.get(tool)
        while True:
            attempts += 1
            transient = fault == "timeout" or (fault == "timeout_once" and tool not in self._faulted)
            if fault == "fail" or transient:
                self._faulted.add(tool)
                if attempts <= failure.get("max_retries", 0) and fault != "fail":
                    continue
                step |= {"decision": "failed", "attempts": attempts,
                         "reason": "The integration returned an error" if fault == "fail"
                         else f"Timed out after {attempts} attempt(s)"}
                return step
            break
        step |= {"attempts": attempts, "result": self._run(tool, data)}
        if side_effect:
            self._done[key] = step["n"]
        return step


def redacted_sources(hits: list[SearchHit]) -> tuple[dict[str, SearchHit], int]:
    """Number sources S1..Sn and count how many had instruction-like text removed before any planner sees them."""
    sources = {f"S{i}": h for i, h in enumerate(hits, 1)}
    return sources, sum(1 for h in hits if safety.redact(h.content) != h.content)
