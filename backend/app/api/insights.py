"""Recurring-payment and anomaly-detection endpoints (Phase 3.1). Business logic
lives in app/services/{recurring,anomaly}.py; this stays thin. Phase 7.3: user_id
is derived from the verified JWT, not a client-supplied parameter."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.user import User
from app.schemas.insights import (
    AnomaliesResponse,
    AnomalyItem,
    RecurringPaymentOut,
    RecurringPaymentsResponse,
)
from app.services.anomaly import detect_anomalies
from app.services.auth import get_current_user
from app.services.recurring import detect_and_store_recurring_payments, list_recurring_payments

router = APIRouter(prefix="/api/v1/analytics", tags=["insights"])


@router.post("/recurring/detect", response_model=RecurringPaymentsResponse)
def detect_recurring_endpoint(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RecurringPaymentsResponse:
    rows = detect_and_store_recurring_payments(db, user_id=current_user.id)
    return RecurringPaymentsResponse(items=[RecurringPaymentOut.model_validate(r) for r in rows])


@router.get("/recurring", response_model=RecurringPaymentsResponse)
def list_recurring_endpoint(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RecurringPaymentsResponse:
    rows = list_recurring_payments(db, user_id=current_user.id)
    return RecurringPaymentsResponse(items=[RecurringPaymentOut.model_validate(r) for r in rows])


@router.get("/anomalies", response_model=AnomaliesResponse)
def get_anomalies_endpoint(
    account_id: int | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AnomaliesResponse:
    results = detect_anomalies(db, user_id=current_user.id, account_id=account_id)
    return AnomaliesResponse(items=[AnomalyItem(**r.__dict__) for r in results])
