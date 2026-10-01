"""Pydantic schemas for the ML category classifier endpoints (Phase 4.4) and applying
ML predictions to transactions (Phase 4.5)."""
from pydantic import BaseModel


class TrainingResponse(BaseModel):
    trained: bool
    training_rows: int
    holdout_rows: int
    holdout_accuracy: float | None
    class_counts: dict[str, int]
    message: str


class PredictRequest(BaseModel):
    descriptions: list[str]


class CategoryScore(BaseModel):
    category: str
    confidence: float


class PredictionOut(BaseModel):
    description: str
    predicted_category: str
    confidence: float
    top_categories: list[CategoryScore]


class PredictResponse(BaseModel):
    predictions: list[PredictionOut]


class MLApplyResponse(BaseModel):
    candidates: int
    updated: int
    skipped_not_more_confident: int
    message: str
