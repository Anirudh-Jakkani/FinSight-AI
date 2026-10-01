"""ML category classifier: prediction (Phase 4.4). Loads the model persisted by
train.py and predicts a category + confidence for arbitrary description text."""
from __future__ import annotations

from dataclasses import dataclass

import joblib

from app.ml.train import MODEL_PATH


class ModelNotTrainedError(Exception):
    """No trained model file exists yet — call the training endpoint first."""


@dataclass
class Prediction:
    description: str
    predicted_category: str
    confidence: float
    top_categories: list[tuple[str, float]]


def _load_model():
    if not MODEL_PATH.exists():
        raise ModelNotTrainedError(
            f"No trained model found ({MODEL_PATH.name}); train the classifier first "
            f"via POST /api/v1/ml/train."
        )
    return joblib.load(MODEL_PATH)


def predict_categories(descriptions: list[str], *, top_n: int = 3) -> list[Prediction]:
    pipeline = _load_model()
    probabilities = pipeline.predict_proba(descriptions)
    classes = pipeline.classes_

    results = []
    for description, probs in zip(descriptions, probabilities):
        ranked = sorted(zip(classes, probs), key=lambda cp: cp[1], reverse=True)
        top_category, top_confidence = ranked[0]
        results.append(
            Prediction(
                description=description,
                predicted_category=top_category,
                confidence=round(float(top_confidence), 4),
                top_categories=[(c, round(float(p), 4)) for c, p in ranked[:top_n]],
            )
        )
    return results
