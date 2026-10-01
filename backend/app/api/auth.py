"""User authentication endpoints (Phase 7.1). Business logic lives in
app/services/auth.py; this stays thin. These are new, additive endpoints — no
existing route's behavior changes; every pre-existing endpoint still takes a
plain user_id and requires no token.

Phase 8.5: signup/login are rate-limited by IP (see app/rate_limit.py) — these
are the classic brute-force/mass-account-creation targets an unauthenticated
caller can hit. The `request` parameter name was freed up for slowapi's
required `Request` injection by renaming the body parameter to `payload`.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.account import Account
from app.models.user import User
from app.rate_limit import limiter
from app.schemas.auth import LoginRequest, SignupRequest, TokenResponse, UserOut
from app.services.auth import AuthError, AuthNotConfiguredError, get_current_user, login, signup

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/signup", response_model=TokenResponse, status_code=201)
@limiter.limit("3/minute")
def signup_endpoint(request: Request, payload: SignupRequest, db: Session = Depends(get_db)) -> TokenResponse:
    try:
        result = signup(db, email=payload.email, password=payload.password, currency=payload.currency)
    except AuthNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except AuthError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return TokenResponse(
        access_token=result.access_token,
        user_id=result.user_id,
        account_id=result.account_id,
        email=result.email,
    )


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
def login_endpoint(request: Request, payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    try:
        result = login(db, email=payload.email, password=payload.password)
    except AuthNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return TokenResponse(access_token=result.access_token, user_id=result.user_id, email=result.email)


@router.get("/me", response_model=UserOut)
def me_endpoint(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UserOut:
    # The frontend's authoritative source for account_id (bug: it previously
    # cached this in localStorage only at signup time — never set at all on
    # login, and never re-validated against who's actually logged in — so a
    # stale or absent value silently fell back to a hardcoded demo account id,
    # breaking upload/pipeline for any other real account). Takes the first
    # account by id: today's signup() gives every user exactly one.
    account = db.execute(
        select(Account).where(Account.user_id == current_user.id).order_by(Account.id)
    ).scalars().first()
    return UserOut(
        id=current_user.id,
        email=current_user.email,
        created_at=current_user.created_at,
        account_id=account.id if account else None,
    )
