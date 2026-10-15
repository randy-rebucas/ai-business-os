"""Structure-aware chunking and rule-based classification (pipeline steps 6–7).

Chunks never span a heading change, tables are split by rows with the header repeated, and every chunk carries its
heading path so a citation can name the section. The heading path is also prefixed to the chunk text, which helps
both keyword and vector retrieval match "what section is this".
"""

import re
from dataclasses import dataclass, field

from abos.knowledge import safety
from abos.knowledge.parsing import Block

TARGET_CHARS = 900
MAX_CHARS = 1600


@dataclass
class Chunk:
    content: str
    section: str | None
    page: int | None
    kind: str = "text"
    flags: list[str] = field(default_factory=list)


def _split_long(text: str) -> list[str]:
    if len(text) <= MAX_CHARS:
        return [text]
    parts, cur = [], ""
    for s in re.split(r"(?<=[.!?])\s+", text):
        while len(s) > MAX_CHARS:  # a single huge "sentence" (e.g. no punctuation)
            parts.append(s[:MAX_CHARS])
            s = s[MAX_CHARS:]
        if cur and len(cur) + len(s) + 1 > TARGET_CHARS:
            parts.append(cur)
            cur = s
        else:
            cur = f"{cur} {s}".strip()
    if cur:
        parts.append(cur)
    return parts


def chunk(blocks: list[Block]) -> list[Chunk]:
    out: list[Chunk] = []
    path: list[tuple[int, str]] = []
    buf: list[str] = []
    buf_page: int | None = None

    def section() -> str | None:
        return " > ".join(t for _, t in path) or None

    def emit(text: str, page: int | None, kind: str = "text") -> None:
        sec = section()
        content = f"{sec}\n\n{text}" if sec else text
        flags = ["instruction_like_text"] if safety.is_instruction_like(text) else []
        out.append(Chunk(content, sec, page, kind, flags))

    def flush() -> None:
        nonlocal buf_page
        if buf:
            for part in _split_long(" ".join(buf)) if len(" ".join(buf)) > MAX_CHARS else ["\n\n".join(buf)]:
                emit(part, buf_page)
        buf.clear()
        buf_page = None

    for b in blocks:
        if b.kind == "heading":
            flush()
            path = [(lvl, t) for lvl, t in path if lvl < b.level] + [(b.level, b.text[:120])]
        elif b.kind == "table":
            flush()
            header, rows = (b.rows[0], b.rows[1:]) if len(b.rows) > 1 else ([], b.rows)
            head = "| " + " | ".join(header) + " |" if header else ""
            group: list[str] = []
            for r in rows or [header]:
                line = "| " + " | ".join(r) + " |"
                if group and len(head) + sum(len(x) + 1 for x in group) + len(line) > MAX_CHARS:
                    emit("\n".join([head, *group]).strip(), b.page, "table")
                    group = []
                group.append(line)
            if group:
                emit("\n".join([head, *group]).strip(), b.page, "table")
        else:
            if buf and (sum(len(x) for x in buf) + len(b.text) > TARGET_CHARS or b.page != buf_page):
                flush()
            if not buf:
                buf_page = b.page
            buf.append(b.text)
    flush()
    return out


# ---- classification (step 6) -----------------------------------------------------------------------------------

_TYPES: dict[str, tuple[str, ...]] = {
    "sop": ("standard operating procedure", "sop", "procedure", "step 1", "steps", "checklist", "how to"),
    "policy": ("policy", "policies", "must", "prohibited", "compliance", "applies to", "threshold", "approval"),
    "handbook": ("handbook", "employee", "leave", "benefits", "code of conduct", "working hours"),
    "pricing": ("price list", "pricing", "price", "rate card", "discount", "per unit", "unit price"),
    "catalog": ("catalog", "catalogue", "product", "sku", "specification", "model"),
    "contract": ("agreement", "contract", "party", "parties", "hereby", "term and termination", "supplier"),
    "financial": ("balance sheet", "income statement", "revenue", "profit", "cash flow", "invoice", "receivable"),
    "org_chart": ("organization chart", "org chart", "reports to", "organizational structure"),
    "job_description": ("job description", "responsibilities", "qualifications", "reports to", "role summary"),
    "script": ("script", "greeting", "say:", "customer:", "agent:", "objection"),
    "workflow": ("workflow", "process flow", "handoff", "escalate", "escalation"),
}


def classify(title: str, text: str) -> str:
    sample = f"{title}\n{title}\n{text[:6000]}".lower()
    scores = {t: sum(sample.count(k) for k in kws) for t, kws in _TYPES.items()}
    best, score = max(scores.items(), key=lambda kv: kv[1])
    return best if score >= 2 else "other"
