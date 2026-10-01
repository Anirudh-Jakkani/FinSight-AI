"""Financial analytics (Phase 3): SQL aggregations + light Python post-processing over
stored transactions. Numbers are computed here in SQL/Python only (architecture rule:
"numbers are computed in Python/SQL; the LLM only explains verified results" — no
ML/AI in this phase).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import Select, case, func, select
from sqlalchemy.orm import Session

from app.models.enums import TransactionType
from app.models.transaction import Transaction

UNCATEGORIZED_LABEL = "Uncategorized"

_ORDER_ID_RE = re.compile(r"#\d+")
_TRAILING_NUM_RE = re.compile(r"\b\d{2,}\b")
_WHITESPACE_RE = re.compile(r"\s+")


def _normalize_merchant(description: str) -> str:
    """Best-effort merchant name for grouping, e.g. 'SWIGGY*ORDER #5506' -> 'SWIGGY',
    'AMAZON PAY 296' -> 'AMAZON PAY'. The `merchant` column (Phase 2 schema) isn't
    populated by ingestion yet — this is presentation-only, never written back."""
    text = description.split("*")[0]
    text = _ORDER_ID_RE.sub("", text)
    text = _TRAILING_NUM_RE.sub("", text)
    return _WHITESPACE_RE.sub(" ", text).strip()


def _scope(
    stmt: Select,
    *,
    user_id: int,
    account_id: int | None,
    date_from: date | None,
    date_to: date | None,
) -> Select:
    stmt = stmt.where(Transaction.user_id == user_id)
    if account_id is not None:
        stmt = stmt.where(Transaction.account_id == account_id)
    if date_from is not None:
        stmt = stmt.where(Transaction.transaction_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(Transaction.transaction_date <= date_to)
    return stmt


def _savings_rate(income: Decimal, savings: Decimal) -> float | None:
    if income <= 0:
        return None
    return float(savings / income)


@dataclass
class Summary:
    transaction_count: int
    total_income: Decimal
    total_expenses: Decimal
    savings: Decimal
    savings_rate: float | None


def get_summary(
    db: Session,
    *,
    user_id: int,
    account_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> Summary:
    income_expr = func.coalesce(
        func.sum(case((Transaction.transaction_type == TransactionType.CREDIT, Transaction.amount), else_=0)), 0
    )
    expense_expr = func.coalesce(
        func.sum(case((Transaction.transaction_type == TransactionType.DEBIT, Transaction.amount), else_=0)), 0
    )
    stmt = _scope(
        select(func.count(Transaction.id), income_expr, expense_expr),
        user_id=user_id, account_id=account_id, date_from=date_from, date_to=date_to,
    )
    count, income, expenses = db.execute(stmt).one()
    income = Decimal(income)
    expenses = Decimal(expenses)
    savings = income - expenses
    return Summary(
        transaction_count=count,
        total_income=income,
        total_expenses=expenses,
        savings=savings,
        savings_rate=_savings_rate(income, savings),
    )


@dataclass
class CategorySpending:
    category: str
    total_amount: Decimal
    transaction_count: int
    percent_of_expenses: float


def get_spending_by_category(
    db: Session,
    *,
    user_id: int,
    account_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[CategorySpending]:
    category_expr = func.coalesce(Transaction.category, UNCATEGORIZED_LABEL)
    stmt = _scope(
        select(category_expr.label("category"), func.sum(Transaction.amount), func.count(Transaction.id))
        .where(Transaction.transaction_type == TransactionType.DEBIT)
        .group_by(category_expr)
        .order_by(func.sum(Transaction.amount).desc()),
        user_id=user_id, account_id=account_id, date_from=date_from, date_to=date_to,
    )
    rows = db.execute(stmt).all()
    total_expenses = sum((row[1] for row in rows), Decimal(0))
    return [
        CategorySpending(
            category=row[0],
            total_amount=row[1],
            transaction_count=row[2],
            percent_of_expenses=float(row[1] / total_expenses) if total_expenses > 0 else 0.0,
        )
        for row in rows
    ]


@dataclass
class MonthlyTrend:
    period: str
    income: Decimal
    expenses: Decimal
    savings: Decimal
    savings_rate: float | None


def get_monthly_trends(
    db: Session,
    *,
    user_id: int,
    account_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[MonthlyTrend]:
    # 'YYYY-MM' matches the `period` format already documented for financial_snapshots
    # in docs/database-schema.md, even though this phase computes it live, not stored.
    period_expr = func.to_char(Transaction.transaction_date, "YYYY-MM")
    income_expr = func.coalesce(
        func.sum(case((Transaction.transaction_type == TransactionType.CREDIT, Transaction.amount), else_=0)), 0
    )
    expense_expr = func.coalesce(
        func.sum(case((Transaction.transaction_type == TransactionType.DEBIT, Transaction.amount), else_=0)), 0
    )
    stmt = _scope(
        select(period_expr.label("period"), income_expr, expense_expr)
        .group_by(period_expr)
        .order_by(period_expr),
        user_id=user_id, account_id=account_id, date_from=date_from, date_to=date_to,
    )
    rows = db.execute(stmt).all()
    results = []
    for period, income, expenses in rows:
        income = Decimal(income)
        expenses = Decimal(expenses)
        savings = income - expenses
        results.append(
            MonthlyTrend(
                period=period, income=income, expenses=expenses,
                savings=savings, savings_rate=_savings_rate(income, savings),
            )
        )
    return results


@dataclass
class TopMerchant:
    merchant: str
    total_amount: Decimal
    transaction_count: int


def get_top_merchants(
    db: Session,
    *,
    user_id: int,
    account_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 10,
) -> list[TopMerchant]:
    """Spending (DEBIT only) grouped by merchant. Salary/rent transfers aren't
    'merchants' in the everyday sense, so CREDIT rows are excluded here."""
    label_expr = func.coalesce(Transaction.merchant, Transaction.description_clean, Transaction.description_raw)
    stmt = _scope(
        select(label_expr, Transaction.amount).where(Transaction.transaction_type == TransactionType.DEBIT),
        user_id=user_id, account_id=account_id, date_from=date_from, date_to=date_to,
    )
    totals: dict[str, Decimal] = {}
    counts: dict[str, int] = {}
    for raw_label, amount in db.execute(stmt).all():
        merchant = _normalize_merchant(raw_label)
        totals[merchant] = totals.get(merchant, Decimal(0)) + amount
        counts[merchant] = counts.get(merchant, 0) + 1

    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:limit]
    return [TopMerchant(merchant=name, total_amount=total, transaction_count=counts[name]) for name, total in ranked]
