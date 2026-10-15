"""Validated financial calculations (SPEC §2, §6 'Financial safety'): figures come from this logic, never a model.

Exact `Decimal` arithmetic, quantised to cents. Pure functions over plain dicts so the simulation sandbox (fixtures)
and the real tools (database records) check invoices the same way.
"""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

CENT = Decimal("0.01")
AGING_BUCKETS = ((0, "current"), (30, "1-30"), (60, "31-60"), (90, "61-90"))  # upper bound inclusive → label


def money(value: Any) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def line_amount(quantity: Any, unit_price: Any) -> Decimal:
    return money(Decimal(str(quantity)) * Decimal(str(unit_price)))


def invoice_checks(record: dict) -> list[str]:
    """Discrepancies in an invoice record: lines vs total, payments vs balance."""
    out = []
    try:
        lines = [Decimal(str(x["amount"])) for x in record.get("lines", [])]
        total = Decimal(str(record["total"])) if "total" in record else None
        if lines and total is not None and sum(lines) != total:
            out.append(f"Invoice {record.get('number', record.get('id'))}: lines add up to {sum(lines)} but the "
                       f"total is {total}")
        if "paid" in record and "balance" in record and total is not None:
            if total - Decimal(str(record["paid"])) != Decimal(str(record["balance"])):
                out.append(f"Invoice {record.get('number', record.get('id'))}: total {total} minus paid "
                           f"{record['paid']} is not the recorded balance {record['balance']}")
    except (KeyError, InvalidOperation, TypeError):
        out.append(f"Invoice {record.get('id')}: amounts could not be validated")
    return out


def days_overdue(due: date, today: date, balance: Decimal) -> int:
    return max(0, (today - due).days) if balance > 0 else 0


def aging_bucket(days: int) -> str:
    for limit, label in AGING_BUCKETS:
        if days <= limit:
            return label
    return "90+"


def follow_up_priority(days: int, balance: Decimal) -> str:
    """Deterministic categorisation for the receivables review (SPEC step 4 example task)."""
    if days == 0:
        return "none"
    if days > 60:
        return "high"
    return "medium" if days > 30 else "low"


def totals_by_currency(rows: list[dict], field: str) -> dict[str, str]:
    """{currency: sum} as strings — amounts in different currencies are never added together."""
    out: dict[str, Decimal] = {}
    for r in rows:
        out[r["currency"]] = out.get(r["currency"], Decimal(0)) + Decimal(str(r[field]))
    return {c: str(money(v)) for c, v in sorted(out.items())}
