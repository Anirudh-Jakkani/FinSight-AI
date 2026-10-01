"""Pydantic schemas for expense forecasting (Phase 3.3)."""
from decimal import Decimal

from pydantic import BaseModel


class ForecastPointOut(BaseModel):
    period: str
    predicted_expenses: Decimal


class ExpenseForecastResponse(BaseModel):
    method: str
    historical_periods: list[str]
    historical_expenses: list[Decimal]
    forecast: list[ForecastPointOut]
    explanation: str
    slope: float | None = None
    intercept: float | None = None
    r_squared: float | None = None
