"""Financial analytics endpoints. Business logic lives in app/services; this stays
thin. Phase 7.3: user_id is derived from the verified JWT (get_current_user), not
a client-supplied parameter — see app/api/transactions.py's module docstring for
the full rationale."""
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.user import User
from app.schemas.analytics import (
    CategorySpendingItem,
    CategorySpendingResponse,
    MonthlyTrendItem,
    MonthlyTrendsResponse,
    SummaryResponse,
    TopMerchantItem,
    TopMerchantsResponse,
)
from app.services import analytics as analytics_service
from app.services.auth import get_current_user

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


@router.get("/summary", response_model=SummaryResponse)
def get_summary_endpoint(
    account_id: int | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SummaryResponse:
    result = analytics_service.get_summary(
        db, user_id=current_user.id, account_id=account_id, date_from=date_from, date_to=date_to
    )
    return SummaryResponse(**result.__dict__)


@router.get("/spending-by-category", response_model=CategorySpendingResponse)
def get_spending_by_category_endpoint(
    account_id: int | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CategorySpendingResponse:
    results = analytics_service.get_spending_by_category(
        db, user_id=current_user.id, account_id=account_id, date_from=date_from, date_to=date_to
    )
    return CategorySpendingResponse(items=[CategorySpendingItem(**r.__dict__) for r in results])


@router.get("/monthly-trends", response_model=MonthlyTrendsResponse)
def get_monthly_trends_endpoint(
    account_id: int | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MonthlyTrendsResponse:
    results = analytics_service.get_monthly_trends(
        db, user_id=current_user.id, account_id=account_id, date_from=date_from, date_to=date_to
    )
    return MonthlyTrendsResponse(items=[MonthlyTrendItem(**r.__dict__) for r in results])


@router.get("/top-merchants", response_model=TopMerchantsResponse)
def get_top_merchants_endpoint(
    account_id: int | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    limit: int = Query(10, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TopMerchantsResponse:
    results = analytics_service.get_top_merchants(
        db, user_id=current_user.id, account_id=account_id, date_from=date_from, date_to=date_to, limit=limit
    )
    return TopMerchantsResponse(items=[TopMerchantItem(**r.__dict__) for r in results])
