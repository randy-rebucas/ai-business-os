"""Treat document text as untrusted data (SPEC §6 RAG security).

Uploaded documents can contain instructions aimed at the model ("ignore previous instructions…"). Three layers:
1. Ingestion flags chunks containing instruction-like text and warns the reviewer (`instruction_like_text`).
2. Before any source text reaches a model, those sentences are replaced with a placeholder (`redact`).
3. The answer prompt marks sources as data and the answer is validated deterministically afterwards
   (citations must quote retrieved text; see knowledge/answer.py).
Pattern matching is a heuristic, not a guarantee — layers 2 and 3 exist because layer 1 can miss things.
"""

import re

_PATTERNS = [
    r"\bignore\s+(all\s+|any\s+|the\s+)?(previous|prior|above|earlier)\s+(instructions?|rules?|prompts?)",
    r"\bdisregard\s+(all\s+|any\s+|the\s+)?(previous|prior|above|earlier|your)\b",
    r"\bforget\s+(all\s+|your\s+)?(previous|prior)?\s*(instructions?|rules?)",
    r"\byou\s+are\s+now\s+(a|an|the)\b",
    r"\b(reveal|print|show|output|repeat)\s+(your|the)\s+(system\s+prompt|instructions|api\s*keys?|credentials|secrets?)",
    r"\bsystem\s+prompt\b",
    r"\b(new|updated)\s+instructions?\s*:",
    r"\bact\s+as\s+(if\s+you\s+are\s+)?(a|an|the)\s+\w+",
    r"\b(respond|reply|answer)\s+(only\s+)?with\b",
    r"\bdo\s+not\s+(tell|inform)\s+the\s+user\b",
    r"\b(transfer|send|wire)\s+(the\s+)?(money|funds|payment)\s+to\b",
    r"<\s*/?\s*(system|instructions?|assistant)\s*>",
]
_RX = re.compile("|".join(_PATTERNS), re.IGNORECASE)
_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")
PLACEHOLDER = "[instruction-like text removed]"


def sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE.split(text) if s.strip()]


def is_instruction_like(text: str) -> bool:
    return bool(_RX.search(text))


def redact(text: str) -> str:
    if not is_instruction_like(text):
        return text
    return " ".join(PLACEHOLDER if is_instruction_like(s) else s for s in sentences(text))
