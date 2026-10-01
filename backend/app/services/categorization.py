"""Rule-based transaction categorizer (Phase 2.3): deterministic keyword matching only,
no ML/statistics. category_source is always CategorySource.RULE here; a later phase may
add a learned classifier that sets CategorySource.ML instead, and never overwrites a row
a user has corrected (CategorySource.USER).

Usage:
    python -m app.services.categorization
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import CategorySource
from app.models.transaction import Transaction

CONFIDENCE_REVIEW_THRESHOLD = 0.7
DEFAULT_CATEGORY = "Other"
DEFAULT_CONFIDENCE = 0.3

# Ordered: more specific keywords must come before broader catch-alls so, e.g.,
# "AMAZON PRIME MEMBERSHIP" is caught by Entertainment before Shopping's generic "AMAZON".
_RULES: list[tuple[str, list[str], float]] = [
    ("Salary", ["SALARY", "PAYROLL"], 0.97),
    ("Rent", ["RENT TRANSFER", "RENT PAYMENT", "RENT"], 0.95),
    ("Entertainment", [
        "NETFLIX", "SPOTIFY", "AMAZON PRIME", "PRIME VIDEO", "HOTSTAR",
        "YOUTUBE PREMIUM", "BOOKMYSHOW", "PVR", "INOX",
    ], 0.9),
    ("Food", [
        "SWIGGY", "ZOMATO", "DOMINOS", "PIZZA", "RESTAURANT", "CAFE",
        "STARBUCKS", "MCDONALD", "KFC", "BURGER",
    ], 0.9),
    ("Transport", [
        "UBER", "OLA", "RAPIDO", "METRO", "PETROL", "FUEL", "IRCTC",
        "INDIGO", "REDBUS", "PARKING",
    ], 0.9),
    ("Bills", [
        "ELECTRICITY", "MSEDCL", "AIRTEL", "JIO", "VODAFONE", "BSNL",
        "BROADBAND", "WATER BILL", "GAS BILL", "DTH", "POSTPAID",
    ], 0.9),
    ("Healthcare", [
        "PHARMACY", "APOLLO", "HOSPITAL", "CLINIC", "MEDPLUS",
        "DIAGNOSTIC", "MEDICAL",
    ], 0.9),
    ("Education", ["UDEMY", "COURSERA", "TUITION", "SCHOOL FEE", "COLLEGE", "BYJU"], 0.9),
    ("Shopping", ["AMAZON PAY", "AMAZON", "FLIPKART", "MYNTRA", "AJIO", "MEESHO"], 0.8),
    # Weak/generic signal: still a best guess, but low enough confidence to force review.
    ("Shopping", ["STORE", "MALL"], 0.55),
]

_compiled = [
    (category, [re.compile(r"\b" + re.escape(kw) + r"\b") for kw in keywords], confidence)
    for category, keywords, confidence in _RULES
]


@dataclass
class CategorizationResult:
    category: str
    confidence: float
    needs_review: bool


def categorize_description(description: str) -> CategorizationResult:
    normalized = description.upper()
    for category, patterns, confidence in _compiled:
        if any(p.search(normalized) for p in patterns):
            return CategorizationResult(category, confidence, confidence < CONFIDENCE_REVIEW_THRESHOLD)
    return CategorizationResult(DEFAULT_CATEGORY, DEFAULT_CONFIDENCE, True)


def categorize_transactions(db: Session, *, user_id: int | None = None, recategorize: bool = False) -> int:
    """Categorizes matching transactions in place and commits. By default only touches rows
    with category IS NULL, so it never clobbers a user correction or an ML result; pass
    recategorize=True to also re-run over rows this same rule engine previously labeled."""
    query = select(Transaction)
    if user_id is not None:
        query = query.where(Transaction.user_id == user_id)
    if recategorize:
        query = query.where(
            Transaction.category.is_(None) | (Transaction.category_source == CategorySource.RULE)
        )
    else:
        query = query.where(Transaction.category.is_(None))

    transactions = db.execute(query).scalars().all()
    for txn in transactions:
        result = categorize_description(txn.description_clean or txn.description_raw)
        txn.category = result.category
        txn.category_confidence = result.confidence
        txn.category_source = CategorySource.RULE
        txn.needs_review = result.needs_review

    if transactions:
        db.commit()
    return len(transactions)


if __name__ == "__main__":
    from app.db.database import SessionLocal

    session = SessionLocal()
    try:
        count = categorize_transactions(session)
        print(f"Categorized {count} transaction(s).")
    finally:
        session.close()
