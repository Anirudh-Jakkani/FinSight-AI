"""Anomaly detection (Phase 3.1): flags DEBIT transactions whose amount is a
statistical outlier relative to other transactions in the *same category* — comparing
apples to apples (Rent being larger than Food isn't an anomaly; an unusually large
Food purchase is). Computed live; docs/database-schema.md defines no table for this
(unlike recurring_payments), so nothing is persisted.

Uses a median/MAD-based robust z-score rather than mean/stdev: two co-occurring
outliers in the same category otherwise inflate the stdev enough to mask each other
(verified against this project's sample data — a second planted anomaly scored 2.36
under classic z-score, just under a 2.5 threshold, and only appeared once the
mean/stdev were swapped for median/MAD, which resists exactly this distortion).
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import TransactionType
from app.models.transaction import Transaction

MIN_CATEGORY_SAMPLE = 5
Z_SCORE_THRESHOLD = 2.5
# Scales MAD to be comparable to stdev under a roughly-normal distribution (standard constant).
_MAD_SCALE = 1.4826


@dataclass
class AnomalyResult:
    transaction_id: int
    transaction_date: date
    description_raw: str
    category: str
    amount: Decimal
    category_mean: Decimal
    category_stdev: Decimal
    z_score: float


def detect_anomalies(
    db: Session, *, user_id: int, account_id: int | None = None
) -> list[AnomalyResult]:
    stmt = select(Transaction).where(
        Transaction.user_id == user_id,
        Transaction.transaction_type == TransactionType.DEBIT,
        Transaction.category.is_not(None),
    )
    if account_id is not None:
        stmt = stmt.where(Transaction.account_id == account_id)

    transactions = list(db.execute(stmt).scalars())

    by_category: dict[str, list[Transaction]] = {}
    for txn in transactions:
        by_category.setdefault(txn.category, []).append(txn)

    results: list[AnomalyResult] = []
    for category, txns in by_category.items():
        if len(txns) < MIN_CATEGORY_SAMPLE:
            continue
        amounts = [float(t.amount) for t in txns]
        median = statistics.median(amounts)
        mad = statistics.median([abs(a - median) for a in amounts])
        scaled_mad = mad * _MAD_SCALE
        if scaled_mad == 0:
            continue
        for txn, amount in zip(txns, amounts):
            z = (amount - median) / scaled_mad
            if abs(z) > Z_SCORE_THRESHOLD:
                results.append(
                    AnomalyResult(
                        transaction_id=txn.id,
                        transaction_date=txn.transaction_date,
                        description_raw=txn.description_raw,
                        category=category,
                        amount=txn.amount,
                        category_mean=Decimal(str(round(median, 2))),
                        category_stdev=Decimal(str(round(scaled_mad, 2))),
                        z_score=round(z, 2),
                    )
                )

    results.sort(key=lambda r: abs(r.z_score), reverse=True)
    return results
