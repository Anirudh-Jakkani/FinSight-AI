"""ML category classifier: training (Phase 4.4). TF-IDF + Naive Bayes over
description text, trained on already-labeled transactions (any category_source —
rule, user, or a prior ml run). This complements, not replaces, the rule-based
categorizer (app/services/categorization.py): per docs/architecture.md, "ML |
backend/app/ml/ | TF-IDF classifier training/prediction" is its own layer, meant as a
learned fallback for text the fixed keyword rules don't confidently match — nothing
here writes back to the transactions table.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import Pipeline
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.transaction import Transaction

MODEL_DIR = Path(__file__).resolve().parent / "models"
MODEL_PATH = MODEL_DIR / "category_classifier.joblib"
MIN_TRAINING_ROWS = 10
TEST_SIZE = 0.2
RANDOM_STATE = 42


@dataclass
class TrainingResult:
    trained: bool
    training_rows: int
    holdout_rows: int
    holdout_accuracy: float | None
    class_counts: dict[str, int]
    message: str


def _load_labeled_text(db: Session) -> tuple[list[str], list[str]]:
    rows = db.execute(
        select(Transaction.description_clean, Transaction.description_raw, Transaction.category).where(
            Transaction.category.is_not(None)
        )
    ).all()
    texts = [clean or raw for clean, raw, _ in rows]
    labels = [category for _, _, category in rows]
    return texts, labels


def train_classifier(db: Session) -> TrainingResult:
    texts, labels = _load_labeled_text(db)

    class_counts: dict[str, int] = {}
    for label in labels:
        class_counts[label] = class_counts.get(label, 0) + 1

    if len(texts) < MIN_TRAINING_ROWS:
        return TrainingResult(
            trained=False,
            training_rows=len(texts),
            holdout_rows=0,
            holdout_accuracy=None,
            class_counts=class_counts,
            message=(
                f"Only {len(texts)} labeled transactions found (need at least "
                f"{MIN_TRAINING_ROWS}); skipped training."
            ),
        )

    # sklearn's stratify requires every class to have >=2 members; several categories
    # here have very few examples (e.g. Education has 1), so fall back to a plain
    # random split when that condition isn't met rather than erroring out.
    can_stratify = len(class_counts) > 1 and all(count >= 2 for count in class_counts.values())
    try:
        x_train, x_test, y_train, y_test = train_test_split(
            texts,
            labels,
            test_size=TEST_SIZE,
            random_state=RANDOM_STATE,
            stratify=labels if can_stratify else None,
        )
    except ValueError:
        x_train, x_test, y_train, y_test = texts, [], labels, []

    pipeline = Pipeline(
        [
            ("tfidf", TfidfVectorizer(lowercase=True, ngram_range=(1, 2), min_df=1)),
            ("clf", MultinomialNB()),
        ]
    )
    pipeline.fit(x_train, y_train)

    holdout_accuracy = None
    if x_test:
        predictions = pipeline.predict(x_test)
        holdout_accuracy = float(accuracy_score(y_test, predictions))

    # Holdout split above was only to honestly measure accuracy; the deployed model
    # is refit on every labeled example available, not just the training split.
    pipeline.fit(texts, labels)

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, MODEL_PATH)

    return TrainingResult(
        trained=True,
        training_rows=len(texts),
        holdout_rows=len(x_test),
        holdout_accuracy=holdout_accuracy,
        class_counts=class_counts,
        message=f"Trained on {len(texts)} labeled transactions across {len(class_counts)} categories.",
    )
