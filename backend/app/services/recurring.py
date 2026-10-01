"""Recurring-payment detection (Phase 3.1): groups transactions by normalized merchant
and flags merchants with a stable, roughly-periodic cadence (monthly bills,
subscriptions, salary, rent) — regardless of CREDIT/DEBIT, since recurring_payments
(docs/database-schema.md) has no type column and salary is a legitimate recurring
inflow. Frequent-but-irregular spending (food delivery, cabs) is excluded by the
interval-regularity check, not by amount.

Results are persisted to recurring_payments; app/services/anomaly.py stays
read-only since no table is defined for anomalies in the schema doc.
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.recurring_payment import RecurringPayment
from app.models.transaction import Transaction

MIN_OCCURRENCES = 3
MIN_AVG_INTERVAL_DAYS = 20
MAX_INTERVAL_COEFFICIENT_OF_VARIATION = 0.35

_ORDER_ID_RE = re.compile(r"#\d+")
_TRAILING_NUM_RE = re.compile(r"\b\d{2,}\b")
_WHITESPACE_RE = re.compile(r"\s+")


def _normalize_merchant(description: str) -> str:
    """Mirrors app/services/analytics.py's normalizer. Duplicated (not imported) so
    this phase doesn't reach into a completed phase's module."""
    text = description.split("*")[0]
    text = _ORDER_ID_RE.sub("", text)
    text = _TRAILING_NUM_RE.sub("", text)
    return _WHITESPACE_RE.sub(" ", text).strip()


@dataclass
class RecurringCandidate:
    merchant: str
    avg_amount: Decimal
    interval_days: int
    last_seen: date
    occurrences: int


def _detect_candidates(rows: list[tuple[str, date, Decimal]]) -> list[RecurringCandidate]:
    groups: dict[str, list[tuple[date, Decimal]]] = {}
    for raw_label, txn_date, amount in rows:
        merchant = _normalize_merchant(raw_label)
        groups.setdefault(merchant, []).append((txn_date, amount))

    candidates: list[RecurringCandidate] = []
    for merchant, entries in groups.items():
        if len(entries) < MIN_OCCURRENCES:
            continue
        entries.sort(key=lambda e: e[0])
        dates = [e[0] for e in entries]
        amounts = [e[1] for e in entries]

        gaps = [(dates[i] - dates[i - 1]).days for i in range(1, len(dates))]
        avg_interval = statistics.mean(gaps)
        if avg_interval < MIN_AVG_INTERVAL_DAYS:
            continue

        stdev = statistics.pstdev(gaps) if len(gaps) > 1 else 0.0
        coefficient_of_variation = stdev / avg_interval if avg_interval else float("inf")
        if coefficient_of_variation > MAX_INTERVAL_COEFFICIENT_OF_VARIATION:
            continue

        avg_amount = (sum(amounts) / len(amounts)).quantize(Decimal("0.01"))
        candidates.append(
            RecurringCandidate(
                merchant=merchant,
                avg_amount=avg_amount,
                interval_days=round(avg_interval),
                last_seen=dates[-1],
                occurrences=len(entries),
            )
        )
    return candidates


def detect_and_store_recurring_payments(db: Session, *, user_id: int) -> list[RecurringPayment]:
    rows = db.execute(
        select(
            func.coalesce(Transaction.merchant, Transaction.description_clean, Transaction.description_raw),
            Transaction.transaction_date,
            Transaction.amount,
        ).where(Transaction.user_id == user_id)
    ).all()

    candidates = _detect_candidates([(r[0], r[1], r[2]) for r in rows])
    detected_merchants = {c.merchant for c in candidates}

    existing = {
        rp.merchant: rp
        for rp in db.execute(
            select(RecurringPayment).where(RecurringPayment.user_id == user_id)
        ).scalars()
    }

    stored: list[RecurringPayment] = []
    for candidate in candidates:
        row = existing.get(candidate.merchant)
        if row is None:
            row = RecurringPayment(user_id=user_id, merchant=candidate.merchant)
            db.add(row)
        row.avg_amount = candidate.avg_amount
        row.interval_days = candidate.interval_days
        row.last_seen = candidate.last_seen
        stored.append(row)

    # Drop rows for merchants that no longer qualify, so the table reflects current data.
    for merchant, row in existing.items():
        if merchant not in detected_merchants:
            db.delete(row)

    db.commit()
    for row in stored:
        db.refresh(row)
    stored.sort(key=lambda r: r.merchant)
    return stored


def list_recurring_payments(db: Session, *, user_id: int) -> list[RecurringPayment]:
    return list(
        db.execute(
            select(RecurringPayment)
            .where(RecurringPayment.user_id == user_id)
            .order_by(RecurringPayment.merchant)
        ).scalars()
    )
