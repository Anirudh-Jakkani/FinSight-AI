"""Pydantic schema for the automated transaction pipeline endpoint (Phase 5)."""
from pydantic import BaseModel

from app.schemas.transaction import TransactionUploadRowError


class PipelineResponse(BaseModel):
    filename: str
    rows_processed: int
    inserted: int
    skipped_duplicates: int
    failed: int
    errors: list[TransactionUploadRowError]
    merchants_cleaned: int
    rows_categorized: int
    ml_candidates: int
    ml_updated: int
    ml_message: str
