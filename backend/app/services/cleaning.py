"""Merchant-name cleaning (the "Cleaner" stage, Phase 4.6): extracts a normalized
merchant name from a transaction's description and persists it to the dedicated
`merchant` column — the one stage in docs/architecture.md's ingestion pipeline
("File parser → Cleaner → Categorizer → PostgreSQL") that was never implemented.
Phase 2.2's ingestion explicitly deferred merchant extraction to this step, and every
transaction has had merchant=NULL until now.

This is presentation-grade normalization (strip order IDs/trailing digits, collapse
whitespace) — it doesn't merge merchants across spelling variants beyond that. The
ad-hoc normalizers already duplicated in app/services/analytics.py and
app/services/recurring.py are left exactly as they are (those are completed phases);
this module is the source of truth going forward for anything that wants the
persisted merchant value instead of recomputing it on the fly.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.transaction import Transaction

_ORDER_ID_RE = re.compile(r"#\d+")
_TRAILING_NUM_RE = re.compile(r"\b\d{2,}\b")
_WHITESPACE_RE = re.compile(r"\s+")


def extract_merchant(description: str) -> str:
    """'SWIGGY*ORDER #5506' -> 'SWIGGY'; 'AMAZON PAY 296' -> 'AMAZON PAY'."""
    text = description.split("*")[0]
    text = _ORDER_ID_RE.sub("", text)
    text = _TRAILING_NUM_RE.sub("", text)
    return _WHITESPACE_RE.sub(" ", text).strip()


@dataclass
class CleaningResult:
    candidates: int
    updated: int


def clean_merchants(db: Session, *, user_id: int | None = None) -> CleaningResult:
    """Populates `merchant` for any transaction where it's still NULL. Never touches
    a row that already has a merchant value — this only fills gaps, it doesn't
    re-derive or override an existing value (e.g. one a future, more precise
    extractor or a user might set)."""
    query = select(Transaction).where(Transaction.merchant.is_(None))
    if user_id is not None:
        query = query.where(Transaction.user_id == user_id)

    candidates = list(db.execute(query).scalars())
    updated = 0
    for txn in candidates:
        merchant = extract_merchant(txn.description_clean or txn.description_raw)
        if merchant:
            txn.merchant = merchant
            updated += 1

    if updated:
        db.commit()
    return CleaningResult(candidates=len(candidates), updated=updated)
