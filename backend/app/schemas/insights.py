"""Pydantic schemas for recurring-payment and anomaly-detection endpoints (Phase 3.1)."""
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class RecurringPaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    merchant: str
    avg_amount: Decimal
    interval_days: int
    last_seen: date


class RecurringPaymentsResponse(BaseModel):
    items: list[RecurringPaymentOut]


class AnomalyItem(BaseModel):
    transaction_id: int
    transaction_date: date
    description_raw: str
    category: str
    amount: Decimal
    category_mean: Decimal
    category_stdev: Decimal
    z_score: float


class AnomaliesResponse(BaseModel):
    items: list[AnomalyItem]
