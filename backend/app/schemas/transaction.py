"""Pydantic schemas for transaction ingestion (Phase 2.2), read/query APIs (Phase 2.4),
category corrections (Phase 4.3), and merchant cleaning (Phase 4.6)."""
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import CategorySource, TransactionType


class TransactionUploadRowError(BaseModel):
    row_number: int
    raw: dict[str, str]
    error: str


class TransactionUploadResponse(BaseModel):
    filename: str
    rows_processed: int
    inserted: int
    skipped_duplicates: int
    failed: int
    errors: list[TransactionUploadRowError]
    inserted_ids: list[int]


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    account_id: int
    transaction_date: date
    description_raw: str
    description_clean: str | None
    merchant: str | None
    amount: Decimal
    transaction_type: TransactionType
    category: str | None
    category_confidence: float | None
    category_source: CategorySource | None
    needs_review: bool
    currency: str
    source_file: str | None
    dedupe_hash: str
    created_at: datetime


class TransactionListResponse(BaseModel):
    total: int
    count: int
    items: list[TransactionOut]


class TransactionDeleteResponse(BaseModel):
    id: int
    deleted: bool


class CategoryCorrectionRequest(BaseModel):
    # Phase 7.3: user_id removed — the acting user is derived from the verified
    # JWT (see app/api/transactions.py), never from a client-supplied value.
    new_category: str = Field(min_length=1)


class MerchantCleaningResponse(BaseModel):
    candidates: int
    updated: int
