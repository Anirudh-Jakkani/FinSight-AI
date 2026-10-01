"""Pydantic schemas for financial snapshot endpoints (Phase 3.2)."""
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class FinancialSnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    period: str
    income: Decimal
    expenses: Decimal
    savings: Decimal
    savings_rate: float | None


class FinancialSnapshotsResponse(BaseModel):
    items: list[FinancialSnapshotOut]
