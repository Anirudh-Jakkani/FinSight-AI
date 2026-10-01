"""AI financial-summary endpoint (Phase 4.1). Business logic lives in
app/services/ai_assistant.py; this stays thin. Always returns 200 — success/error
are reported in the body so callers can still see `based_on` (the verified analytics
that were/would be sent to the model) even when the AI call itself failed.

Phase 7.3: user_id is derived from the verified JWT, not a client-supplied
parameter.

Phase 8.5: rate-limited per authenticated user (see app/rate_limit.py) — this
calls a paid/quota-limited third-party API, which this project has exhausted
the free tier of repeatedly just from normal testing."""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.user import User
from app.rate_limit import limiter
from app.schemas.ai_assistant import AISummaryResponse
from app.services.ai_assistant import generate_financial_summary
from app.services.auth import get_current_user

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])


@router.get("/summary", response_model=AISummaryResponse)
@limiter.limit("10/minute")
def get_ai_summary_endpoint(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AISummaryResponse:
    result = generate_financial_summary(db, user_id=current_user.id)
    return AISummaryResponse(
        success=result.success,
        model=result.model,
        summary=result.summary,
        error=result.error,
        based_on=result.based_on,
    )
