"""Expense forecasting (Phase 3.3): a simple, explainable linear-trend forecast over
monthly expense totals — a single least-squares line, no ML. Falls back safely when
history is too short: 0 months -> explicit "insufficient_data"; 1 month -> repeats
that month (naive carry-forward); 2 months -> flat average (too few points for a
trend line to mean anything). Monthly-expense grouping mirrors
app/services/analytics.py / app/services/snapshots.py (duplicated, not imported, to
keep those completed phases untouched).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.enums import TransactionType
from app.models.transaction import Transaction

MIN_MONTHS_FOR_TREND = 3
MAX_PERIODS_AHEAD = 6


def _get_monthly_expenses(db: Session, *, user_id: int) -> list[tuple[str, Decimal]]:
    period_expr = func.to_char(Transaction.transaction_date, "YYYY-MM")
    expense_expr = func.coalesce(
        func.sum(case((Transaction.transaction_type == TransactionType.DEBIT, Transaction.amount), else_=0)), 0
    )
    rows = db.execute(
        select(period_expr.label("period"), expense_expr)
        .where(Transaction.user_id == user_id)
        .group_by(period_expr)
        .order_by(period_expr)
    ).all()
    return [(period, Decimal(expenses)) for period, expenses in rows]


def _next_period(period: str, offset: int) -> str:
    year, month = (int(p) for p in period.split("-"))
    total = (year * 12 + (month - 1)) + offset
    return f"{total // 12:04d}-{(total % 12) + 1:02d}"


@dataclass
class ForecastPoint:
    period: str
    predicted_expenses: Decimal


@dataclass
class ForecastResult:
    method: str
    historical_periods: list[str]
    historical_expenses: list[Decimal]
    forecast: list[ForecastPoint]
    explanation: str
    slope: float | None = None
    intercept: float | None = None
    r_squared: float | None = None


def _linear_regression(y: list[float]) -> tuple[float, float, float]:
    n = len(y)
    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(y) / n
    denom = sum((x - mean_x) ** 2 for x in xs)
    slope = sum((x - mean_x) * (yi - mean_y) for x, yi in zip(xs, y)) / denom
    intercept = mean_y - slope * mean_x

    ss_tot = sum((yi - mean_y) ** 2 for yi in y)
    ss_res = sum((yi - (intercept + slope * x)) ** 2 for x, yi in zip(xs, y))
    r_squared = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 1.0
    return slope, intercept, r_squared


def forecast_expenses(db: Session, *, user_id: int, periods_ahead: int = 1) -> ForecastResult:
    periods_ahead = max(1, min(periods_ahead, MAX_PERIODS_AHEAD))
    history = _get_monthly_expenses(db, user_id=user_id)
    periods = [p for p, _ in history]
    expenses = [e for _, e in history]

    if not history:
        return ForecastResult(
            method="insufficient_data",
            historical_periods=[],
            historical_expenses=[],
            forecast=[],
            explanation="No transaction history found for this user; cannot forecast.",
        )

    last_period = periods[-1]

    if len(history) == 1:
        value = expenses[0].quantize(Decimal("0.01"))
        forecast = [
            ForecastPoint(period=_next_period(last_period, i), predicted_expenses=value)
            for i in range(1, periods_ahead + 1)
        ]
        return ForecastResult(
            method="naive_last_month",
            historical_periods=periods,
            historical_expenses=expenses,
            forecast=forecast,
            explanation=(
                f"Only 1 month of history ({last_period}); forecast simply repeats that month's "
                f"expense total ({value}). Add more months of data for a trend-based forecast."
            ),
        )

    if len(history) < MIN_MONTHS_FOR_TREND:
        avg = Decimal(str(round(sum(expenses) / len(expenses), 2)))
        forecast = [
            ForecastPoint(period=_next_period(last_period, i), predicted_expenses=avg)
            for i in range(1, periods_ahead + 1)
        ]
        return ForecastResult(
            method="moving_average",
            historical_periods=periods,
            historical_expenses=expenses,
            forecast=forecast,
            explanation=(
                f"Only {len(history)} months of history — too few for a reliable trend line, so the "
                f"forecast is a flat average of those months ({avg})."
            ),
        )

    y = [float(e) for e in expenses]
    slope, intercept, r_squared = _linear_regression(y)
    n = len(y)
    forecast = [
        ForecastPoint(
            period=_next_period(last_period, i + 1),
            predicted_expenses=Decimal(str(round(max(0.0, intercept + slope * (n + i)), 2))),
        )
        for i in range(periods_ahead)
    ]

    direction = "increasing" if slope > 0 else "decreasing" if slope < 0 else "flat"
    explanation = (
        f"Fitted a least-squares linear trend over {n} months of expense data: expenses are "
        f"{direction} by about {abs(slope):.2f}/month (R²={r_squared:.2f}). "
        f"Extrapolated {periods_ahead} month(s) ahead from that line."
    )
    return ForecastResult(
        method="linear_regression",
        historical_periods=periods,
        historical_expenses=expenses,
        forecast=forecast,
        explanation=explanation,
        slope=round(slope, 2),
        intercept=round(intercept, 2),
        r_squared=round(r_squared, 4),
    )
