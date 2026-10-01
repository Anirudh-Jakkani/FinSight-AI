"""Monthly financial snapshots (Phase 3.2): persists one row per (user, 'YYYY-MM'
period) with income/expenses/savings/savings_rate, computed from stored transactions.

The monthly grouping logic mirrors app/services/analytics.py's get_monthly_trends
(duplicated, not imported, to keep that completed phase's module untouched) — the
difference here is persistence: this writes to financial_snapshots via an upsert
keyed on (user_id, period), rather than returning live numbers.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.enums import TransactionType
from app.models.financial_snapshot import FinancialSnapshot
from app.models.transaction import Transaction


def _savings_rate(income: Decimal, savings: Decimal) -> float | None:
    if income <= 0:
        return None
    return float(savings / income)


def generate_and_store_snapshots(db: Session, *, user_id: int) -> list[FinancialSnapshot]:
    period_expr = func.to_char(Transaction.transaction_date, "YYYY-MM")
    income_expr = func.coalesce(
        func.sum(case((Transaction.transaction_type == TransactionType.CREDIT, Transaction.amount), else_=0)), 0
    )
    expense_expr = func.coalesce(
        func.sum(case((Transaction.transaction_type == TransactionType.DEBIT, Transaction.amount), else_=0)), 0
    )
    rows = db.execute(
        select(period_expr.label("period"), income_expr, expense_expr)
        .where(Transaction.user_id == user_id)
        .group_by(period_expr)
        .order_by(period_expr)
    ).all()

    existing = {
        snap.period: snap
        for snap in db.execute(
            select(FinancialSnapshot).where(FinancialSnapshot.user_id == user_id)
        ).scalars()
    }

    detected_periods = {period for period, _, _ in rows}
    stored: list[FinancialSnapshot] = []
    for period, income, expenses in rows:
        income = Decimal(income)
        expenses = Decimal(expenses)
        savings = income - expenses

        snap = existing.get(period)
        if snap is None:
            snap = FinancialSnapshot(user_id=user_id, period=period)
            db.add(snap)
        snap.income = income
        snap.expenses = expenses
        snap.savings = savings
        snap.savings_rate = _savings_rate(income, savings)
        stored.append(snap)

    # Drop snapshots for periods that no longer have any transactions (e.g. after a delete).
    for period, snap in existing.items():
        if period not in detected_periods:
            db.delete(snap)

    db.commit()
    for snap in stored:
        db.refresh(snap)
    stored.sort(key=lambda s: s.period)
    return stored


def list_snapshots(
    db: Session,
    *,
    user_id: int,
    period_from: str | None = None,
    period_to: str | None = None,
) -> list[FinancialSnapshot]:
    stmt = select(FinancialSnapshot).where(FinancialSnapshot.user_id == user_id)
    if period_from is not None:
        stmt = stmt.where(FinancialSnapshot.period >= period_from)
    if period_to is not None:
        stmt = stmt.where(FinancialSnapshot.period <= period_to)
    return list(db.execute(stmt.order_by(FinancialSnapshot.period)).scalars())
