"""Financial snapshot endpoints (Phase 3.2). Business logic lives in
app/services/snapshots.py; this stays thin. Phase 7.3: user_id is derived from
the verified JWT, not a client-supplied parameter."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.user import User
from app.schemas.snapshots import FinancialSnapshotOut, FinancialSnapshotsResponse
from app.services.auth import get_current_user
from app.services.snapshots import generate_and_store_snapshots, list_snapshots

router = APIRouter(prefix="/api/v1/analytics", tags=["snapshots"])


@router.post("/snapshots/generate", response_model=FinancialSnapshotsResponse)
def generate_snapshots_endpoint(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FinancialSnapshotsResponse:
    rows = generate_and_store_snapshots(db, user_id=current_user.id)
    return FinancialSnapshotsResponse(items=[FinancialSnapshotOut.model_validate(r) for r in rows])


@router.get("/snapshots", response_model=FinancialSnapshotsResponse)
def list_snapshots_endpoint(
    period_from: str | None = Query(None, description="YYYY-MM"),
    period_to: str | None = Query(None, description="YYYY-MM"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FinancialSnapshotsResponse:
    rows = list_snapshots(db, user_id=current_user.id, period_from=period_from, period_to=period_to)
    return FinancialSnapshotsResponse(items=[FinancialSnapshotOut.model_validate(r) for r in rows])
