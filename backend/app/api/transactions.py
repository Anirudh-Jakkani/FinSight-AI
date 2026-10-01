"""Transaction ingestion + read/query endpoints. Business logic lives in app/services;
this stays thin.

Phase 7.3: every endpoint here now requires a valid JWT (via get_current_user) and
derives the acting user_id from that verified token rather than a client-supplied
parameter — the parameter itself has been removed from each request. Ownership
checks were already implemented in the service layer (get_transaction/
delete_transaction/correct_category all reject a mismatched user_id as 404); this
phase makes user_id itself trustworthy, which is what actually closes the
cross-user access hole. clean_merchants's user_id=None ("apply to everyone") path
is no longer reachable from this route — an authenticated caller can only ever
target their own data.

Phase 8.5: /upload is rate-limited per authenticated user (see app/rate_limit.py)
— CSV parsing/ingestion is real CPU/DB work an authenticated caller could
otherwise trigger without limit. The read/query/correction endpoints below are
cheap, ordinary DB operations and are left unlimited, same as /auth/me.

Phase 8.6: the upload is read in bounded chunks (see app/upload_limits.py)
instead of one unbounded `.read()` call, so an oversized file is rejected
without ever being fully buffered in memory.
"""
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Path, Query, Request, UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.db.database import get_db
from app.models.enums import TransactionType
from app.models.user import User
from app.rate_limit import limiter
from app.schemas.transaction import (
    CategoryCorrectionRequest,
    MerchantCleaningResponse,
    TransactionDeleteResponse,
    TransactionListResponse,
    TransactionOut,
    TransactionUploadResponse,
    TransactionUploadRowError,
)
from app.services.auth import get_current_user
from app.services.category_correction import CorrectionError, correct_category
from app.services.cleaning import clean_merchants
from app.services.transaction_ingestion import IngestionError, ingest_csv
from app.services.transaction_query import delete_transaction, get_transaction, list_transactions
from app.upload_limits import read_upload_within_limit

router = APIRouter(prefix="/api/v1/transactions", tags=["transactions"])


@router.post("/upload", response_model=TransactionUploadResponse)
@limiter.limit("10/minute")
def upload_transactions(
    request: Request,
    file: UploadFile = File(...),
    account_id: int = Form(...),
    currency: str = Form("INR"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TransactionUploadResponse:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="only .csv files are accepted")

    max_bytes = settings.max_upload_mb * 1024 * 1024
    file_bytes = read_upload_within_limit(file, max_bytes)

    try:
        result = ingest_csv(
            db,
            file_bytes=file_bytes,
            filename=file.filename,
            user_id=current_user.id,
            account_id=account_id,
            currency=currency.strip().upper(),
        )
    except IngestionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return TransactionUploadResponse(
        filename=file.filename,
        rows_processed=result.rows_processed,
        inserted=result.inserted,
        skipped_duplicates=result.skipped_duplicates,
        failed=result.failed,
        errors=[
            TransactionUploadRowError(row_number=e.row_number, raw=e.raw, error=e.error)
            for e in result.errors
        ],
        inserted_ids=result.inserted_ids,
    )


@router.get("", response_model=TransactionListResponse)
def list_transactions_endpoint(
    account_id: int | None = Query(None),
    category: str | None = Query(None),
    transaction_type: TransactionType | None = Query(None),
    needs_review: bool | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TransactionListResponse:
    items, total = list_transactions(
        db,
        user_id=current_user.id,
        account_id=account_id,
        category=category,
        transaction_type=transaction_type,
        needs_review=needs_review,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return TransactionListResponse(total=total, count=len(items), items=items)


@router.get("/{transaction_id}", response_model=TransactionOut)
def get_transaction_endpoint(
    transaction_id: int = Path(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TransactionOut:
    txn = get_transaction(db, transaction_id=transaction_id, user_id=current_user.id)
    if txn is None:
        raise HTTPException(status_code=404, detail="transaction not found")
    return txn


@router.delete("/{transaction_id}", response_model=TransactionDeleteResponse)
def delete_transaction_endpoint(
    transaction_id: int = Path(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TransactionDeleteResponse:
    deleted = delete_transaction(db, transaction_id=transaction_id, user_id=current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="transaction not found")
    return TransactionDeleteResponse(id=transaction_id, deleted=True)


@router.patch("/{transaction_id}/category", response_model=TransactionOut)
def correct_transaction_category_endpoint(
    transaction_id: int,
    request: CategoryCorrectionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TransactionOut:
    try:
        return correct_category(
            db,
            transaction_id=transaction_id,
            user_id=current_user.id,
            new_category=request.new_category,
        )
    except CorrectionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/clean-merchants", response_model=MerchantCleaningResponse)
def clean_merchants_endpoint(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MerchantCleaningResponse:
    result = clean_merchants(db, user_id=current_user.id)
    return MerchantCleaningResponse(candidates=result.candidates, updated=result.updated)
