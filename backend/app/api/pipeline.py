"""Automated transaction pipeline endpoint (Phase 5). Business logic lives in
app/services/pipeline.py, which only sequences existing, unmodified services.

Phase 7.3: user_id is derived from the verified JWT, not a client-supplied
Form field.

Phase 8.5: rate-limited per authenticated user (see app/rate_limit.py) — this
chains ingestion, cleaning, and ML application in one call, making it the
single most expensive endpoint in the app.

Phase 8.6: the upload is read in bounded chunks (see app/upload_limits.py)
instead of one unbounded `.read()` call, so an oversized file is rejected
without ever being fully buffered in memory."""
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.db.database import get_db
from app.models.user import User
from app.rate_limit import limiter
from app.schemas.pipeline import PipelineResponse
from app.schemas.transaction import TransactionUploadRowError
from app.services.auth import get_current_user
from app.services.pipeline import run_pipeline
from app.services.transaction_ingestion import IngestionError
from app.upload_limits import read_upload_within_limit

router = APIRouter(prefix="/api/v1/pipeline", tags=["pipeline"])


@router.post("/run", response_model=PipelineResponse)
@limiter.limit("10/minute")
def run_pipeline_endpoint(
    request: Request,
    file: UploadFile = File(...),
    account_id: int = Form(...),
    currency: str = Form("INR"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PipelineResponse:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="only .csv files are accepted")

    max_bytes = settings.max_upload_mb * 1024 * 1024
    file_bytes = read_upload_within_limit(file, max_bytes)

    try:
        result = run_pipeline(
            db,
            file_bytes=file_bytes,
            filename=file.filename,
            user_id=current_user.id,
            account_id=account_id,
            currency=currency.strip().upper(),
        )
    except IngestionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return PipelineResponse(
        filename=file.filename,
        rows_processed=result.ingestion.rows_processed,
        inserted=result.ingestion.inserted,
        skipped_duplicates=result.ingestion.skipped_duplicates,
        failed=result.ingestion.failed,
        errors=[
            TransactionUploadRowError(row_number=e.row_number, raw=e.raw, error=e.error)
            for e in result.ingestion.errors
        ],
        merchants_cleaned=result.merchants_cleaned.updated,
        rows_categorized=result.rows_categorized,
        ml_candidates=result.ml_apply.candidates,
        ml_updated=result.ml_apply.updated,
        ml_message=result.ml_apply.message,
    )
