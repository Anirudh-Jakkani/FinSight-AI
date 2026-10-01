"""Expense forecasting endpoint (Phase 3.3). Business logic lives in
app/services/forecast.py; this stays thin. Phase 7.3: user_id is derived from
the verified JWT, not a client-supplied parameter."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.user import User
from app.schemas.forecast import ExpenseForecastResponse, ForecastPointOut
from app.services.auth import get_current_user
from app.services.forecast import forecast_expenses

router = APIRouter(prefix="/api/v1/analytics", tags=["forecast"])


@router.get("/forecast/expenses", response_model=ExpenseForecastResponse)
def forecast_expenses_endpoint(
    periods_ahead: int = Query(1, ge=1, le=6),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ExpenseForecastResponse:
    result = forecast_expenses(db, user_id=current_user.id, periods_ahead=periods_ahead)
    return ExpenseForecastResponse(
        method=result.method,
        historical_periods=result.historical_periods,
        historical_expenses=result.historical_expenses,
        forecast=[
            ForecastPointOut(period=p.period, predicted_expenses=p.predicted_expenses)
            for p in result.forecast
        ],
        explanation=result.explanation,
        slope=result.slope,
        intercept=result.intercept,
        r_squared=result.r_squared,
    )
