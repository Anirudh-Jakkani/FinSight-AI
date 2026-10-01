"""Applies the ML classifier (app/ml/predict.py) to transactions the rule engine
(app/services/categorization.py) couldn't confidently label — Phase 4.5. That
module's own docstring anticipated this exactly: "a later phase may add a learned
classifier that sets CategorySource.ML instead, and never overwrites a row a user has
corrected (CategorySource.USER)."

Only ever considers rows with category_source == RULE and needs_review == True (the
same "unsure" bucket the rule engine already flags) — a user's correction is never
touched, and a prediction only replaces the existing guess if it is strictly more
confident than what the rule engine had, so this can only ever improve a label, never
make it worse.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ml.predict import ModelNotTrainedError, predict_categories
from app.models.enums import CategorySource
from app.models.transaction import Transaction

# Mirrors app/services/categorization.py's CONFIDENCE_REVIEW_THRESHOLD (duplicated,
# not imported, to keep that completed phase's module untouched — same pattern used
# across Phases 3.1/3.2/3.3/4.2).
CONFIDENCE_REVIEW_THRESHOLD = 0.7


@dataclass
class MLApplyResult:
    candidates: int
    updated: int
    skipped_not_more_confident: int
    message: str


def apply_ml_categorization(db: Session, *, user_id: int | None = None) -> MLApplyResult:
    query = select(Transaction).where(
        Transaction.category_source == CategorySource.RULE,
        Transaction.needs_review.is_(True),
    )
    if user_id is not None:
        query = query.where(Transaction.user_id == user_id)

    candidates = list(db.execute(query).scalars())
    if not candidates:
        return MLApplyResult(
            candidates=0,
            updated=0,
            skipped_not_more_confident=0,
            message="No rule-flagged needs_review transactions to apply ML to.",
        )

    descriptions = [c.description_clean or c.description_raw for c in candidates]
    try:
        predictions = predict_categories(descriptions)
    except ModelNotTrainedError as exc:
        return MLApplyResult(
            candidates=len(candidates),
            updated=0,
            skipped_not_more_confident=0,
            message=str(exc),
        )

    updated = 0
    skipped = 0
    for txn, prediction in zip(candidates, predictions):
        existing_confidence = txn.category_confidence or 0.0
        if prediction.confidence <= existing_confidence:
            skipped += 1
            continue
        txn.category = prediction.predicted_category
        txn.category_confidence = prediction.confidence
        txn.category_source = CategorySource.ML
        txn.needs_review = prediction.confidence < CONFIDENCE_REVIEW_THRESHOLD
        updated += 1

    db.commit()
    return MLApplyResult(
        candidates=len(candidates),
        updated=updated,
        skipped_not_more_confident=skipped,
        message=(
            f"Updated {updated}/{len(candidates)} transaction(s) via ML "
            f"(strictly more confident than the rule engine's guess); "
            f"{skipped} left as-is."
        ),
    )
