"""ML category classifier endpoints (Phase 4.4) and applying ML predictions to
transactions (Phase 4.5). Business logic lives in app/ml/{train,predict}.py and
app/services/ml_categorization.py; this stays thin.

Phase 7.3: every endpoint here now requires a valid JWT. train/predict operate on
the global classifier (no per-user data), so authentication is the only gate they
need. apply is user-scoped — it used to accept an optional user_id with None
meaning "apply to every user"; that global path is a privilege-escalation risk
once a request is coming from an arbitrary authenticated caller, so it's no longer
reachable here — an authenticated caller can only ever apply ML to their own data.

Phase 8.5: all three are rate-limited per authenticated user (see
app/rate_limit.py) — train is a CPU-heavy full retrain, predict/apply are
cheaper but still real DB/CPU work an authenticated caller could otherwise
hammer without limit. predict_endpoint's body parameter was renamed from
`request` to `payload` to free `request` for slowapi's required `Request`
injection.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.ml.predict import ModelNotTrainedError, predict_categories
from app.ml.train import train_classifier
from app.models.user import User
from app.rate_limit import limiter
from app.schemas.ml import (
    CategoryScore,
    MLApplyResponse,
    PredictionOut,
    PredictRequest,
    PredictResponse,
    TrainingResponse,
)
from app.services.auth import get_current_user
from app.services.ml_categorization import apply_ml_categorization

router = APIRouter(prefix="/api/v1/ml", tags=["ml"])


@router.post("/train", response_model=TrainingResponse)
@limiter.limit("3/minute")
def train_endpoint(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TrainingResponse:
    result = train_classifier(db)
    return TrainingResponse(**result.__dict__)


@router.post("/predict", response_model=PredictResponse)
@limiter.limit("20/minute")
def predict_endpoint(
    request: Request,
    payload: PredictRequest,
    current_user: User = Depends(get_current_user),
) -> PredictResponse:
    if not payload.descriptions:
        raise HTTPException(status_code=422, detail="descriptions must not be empty")

    try:
        predictions = predict_categories(payload.descriptions)
    except ModelNotTrainedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return PredictResponse(
        predictions=[
            PredictionOut(
                description=p.description,
                predicted_category=p.predicted_category,
                confidence=p.confidence,
                top_categories=[
                    CategoryScore(category=c, confidence=conf) for c, conf in p.top_categories
                ],
            )
            for p in predictions
        ]
    )


@router.post("/apply", response_model=MLApplyResponse)
@limiter.limit("10/minute")
def apply_ml_endpoint(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MLApplyResponse:
    result = apply_ml_categorization(db, user_id=current_user.id)
    return MLApplyResponse(**result.__dict__)
