"""Pydantic schemas for financial analytics endpoints (Phase 3)."""
from decimal import Decimal

from pydantic import BaseModel


class SummaryResponse(BaseModel):
    transaction_count: int
    total_income: Decimal
    total_expenses: Decimal
    savings: Decimal
    savings_rate: float | None


class CategorySpendingItem(BaseModel):
    category: str
    total_amount: Decimal
    transaction_count: int
    percent_of_expenses: float


class CategorySpendingResponse(BaseModel):
    items: list[CategorySpendingItem]


class MonthlyTrendItem(BaseModel):
    period: str
    income: Decimal
    expenses: Decimal
    savings: Decimal
    savings_rate: float | None


class MonthlyTrendsResponse(BaseModel):
    items: list[MonthlyTrendItem]


class TopMerchantItem(BaseModel):
    merchant: str
    total_amount: Decimal
    transaction_count: int


class TopMerchantsResponse(BaseModel):
    items: list[TopMerchantItem]
