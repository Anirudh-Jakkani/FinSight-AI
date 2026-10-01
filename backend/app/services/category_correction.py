"""User category corrections (Phase 4.3). Lets a user fix a transaction's category.
Sets category_source to CategorySource.USER, which app/services/categorization.py's
rule engine already treats as protected (categorize_transactions only ever touches
NULL-category or RULE-sourced rows — see its docstring), so a correction here can
never be silently overwritten by a later re-categorization run. Each correction is
also logged to category_corrections (docs/database-schema.md: "stored for future
training; no live retraining is claimed" — this phase only records the data).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.category_correction import CategoryCorrection
from app.models.enums import CategorySource
from app.models.transaction import Transaction


class CorrectionError(Exception):
    """Request-level problem: unknown transaction or wrong owner."""


def correct_category(
    db: Session, *, transaction_id: int, user_id: int, new_category: str
) -> Transaction:
    new_category = new_category.strip()

    transaction = db.get(Transaction, transaction_id)
    if transaction is None or transaction.user_id != user_id:
        raise CorrectionError(f"transaction {transaction_id} not found for this user")

    old_category = transaction.category

    correction = CategoryCorrection(
        transaction_id=transaction.id,
        merchant=transaction.merchant or transaction.description_clean or transaction.description_raw,
        old_category=old_category,
        new_category=new_category,
    )
    db.add(correction)

    transaction.category = new_category
    transaction.category_source = CategorySource.USER
    transaction.category_confidence = 1.0
    transaction.needs_review = False

    db.commit()
    db.refresh(transaction)
    return transaction
