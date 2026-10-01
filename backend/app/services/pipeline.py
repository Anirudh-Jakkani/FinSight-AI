"""Automated transaction pipeline (Phase 5): chains the existing, already-tested
ingestion -> cleaning -> categorization -> ML-apply steps into one call, matching
docs/architecture.md's flow (File parser -> Cleaner -> Categorizer -> PostgreSQL).
Every step below is an unmodified, already-tested service from its own completed
phase (2.2, 4.6, 2.3, 4.5) — this module only sequences them.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.services.categorization import categorize_transactions
from app.services.cleaning import CleaningResult, clean_merchants
from app.services.ml_categorization import MLApplyResult, apply_ml_categorization
from app.services.transaction_ingestion import IngestResult, ingest_csv


@dataclass
class PipelineResult:
    ingestion: IngestResult
    merchants_cleaned: CleaningResult
    rows_categorized: int
    ml_apply: MLApplyResult


def run_pipeline(
    db: Session,
    *,
    file_bytes: bytes,
    filename: str,
    user_id: int,
    account_id: int,
    currency: str,
) -> PipelineResult:
    # IngestionError (bad file/header/unknown user or account) propagates to the caller.
    ingestion = ingest_csv(
        db,
        file_bytes=file_bytes,
        filename=filename,
        user_id=user_id,
        account_id=account_id,
        currency=currency,
    )

    merchants_cleaned = clean_merchants(db, user_id=user_id)
    rows_categorized = categorize_transactions(db, user_id=user_id)
    ml_apply = apply_ml_categorization(db, user_id=user_id)

    return PipelineResult(
        ingestion=ingestion,
        merchants_cleaned=merchants_cleaned,
        rows_categorized=rows_categorized,
        ml_apply=ml_apply,
    )
