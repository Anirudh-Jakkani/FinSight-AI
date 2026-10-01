"""User authentication (Phase 7.1): signup, login, and a get_current_user
dependency for future endpoints to use. This phase is purely additive — no
existing endpoint is retrofitted to require a token; every current route still
takes a plain user_id exactly as before. Passwords are hashed with bcrypt
(salted, deliberately slow); access tokens are signed JWTs.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.database import get_db
from app.models.account import Account
from app.models.user import User

MIN_PASSWORD_LENGTH = 8

_bearer_scheme = HTTPBearer(auto_error=False)
logger = logging.getLogger(__name__)


class AuthError(Exception):
    """Request-level auth problem: duplicate email or bad credentials. Message is
    safe to surface to an API caller — no secrets, no raw exception internals."""


class AuthNotConfiguredError(AuthError):
    """JWT_SECRET_KEY is unset. Distinct from AuthError so the route layer can
    return 503 (deployment misconfigured) instead of 409/401 — a real caller
    shouldn't be told their email is taken or their password is wrong when the
    actual problem is that auth isn't set up at all."""


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def _require_jwt_secret() -> str:
    if not settings.jwt_secret_key:
        raise AuthNotConfiguredError("Authentication is not configured (set JWT_SECRET_KEY in .env).")
    return settings.jwt_secret_key


def create_access_token(user_id: int, email: str) -> str:
    secret = _require_jwt_secret()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "email": email,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    secret = _require_jwt_secret()
    try:
        return jwt.decode(token, secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("Token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthError("Invalid token.") from exc


@dataclass
class SignupResult:
    user_id: int
    account_id: int
    email: str
    access_token: str


def signup(db: Session, *, email: str, password: str, currency: str = "INR") -> SignupResult:
    email = email.strip().lower()
    if len(password) < MIN_PASSWORD_LENGTH:
        raise AuthError(f"password must be at least {MIN_PASSWORD_LENGTH} characters")
    # Fail fast, before any DB write, if auth isn't configured — otherwise a
    # "failed" signup (caller gets no token) would still have silently
    # persisted a real user+account row with no way to ever retrieve a token
    # for it short of a duplicate-email conflict on retry.
    _require_jwt_secret()

    existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if existing is not None:
        # Logged at info, not warning: this is routine ("tried to sign up twice"),
        # not inherently suspicious — but still worth a trail for enumeration patterns.
        logger.info("signup rejected: email already registered (%s)", email)
        raise AuthError("an account with this email already exists")

    user = User(email=email, hashed_password=hash_password(password))
    db.add(user)
    db.flush()  # assigns user.id before the dependent account is created

    account = Account(user_id=user.id, name="Primary", currency=(currency.strip().upper() or "INR"))
    db.add(account)
    db.commit()
    db.refresh(user)
    db.refresh(account)

    token = create_access_token(user.id, user.email)
    logger.info("signup succeeded user_id=%s email=%s", user.id, user.email)
    return SignupResult(user_id=user.id, account_id=account.id, email=user.email, access_token=token)


@dataclass
class LoginResult:
    user_id: int
    email: str
    access_token: str


def login(db: Session, *, email: str, password: str) -> LoginResult:
    email = email.strip().lower()
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None or user.hashed_password is None or not verify_password(password, user.hashed_password):
        # Logged at warning (not the generic message returned to the caller) so
        # repeated failures against one email are visible for brute-force
        # detection — the password itself is never logged, only the fact that
        # an attempt against this email failed.
        logger.warning("login failed for email=%s", email)
        raise AuthError("invalid email or password")

    token = create_access_token(user.id, user.email)
    logger.info("login succeeded user_id=%s", user.id)
    return LoginResult(user_id=user.id, email=user.email, access_token=token)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """FastAPI dependency: resolves a bearer token to a User, or raises 401. Not
    wired into any pre-existing endpoint — this is new, opt-in infrastructure a
    future phase can attach to routes; today it only guards the new /auth/me."""
    if credentials is None:
        raise HTTPException(status_code=401, detail="missing bearer token")
    try:
        payload = decode_access_token(credentials.credentials)
    except AuthNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except AuthError as exc:
        # Never logs the token itself — just that a request was rejected and why
        # (e.g. "Token has expired.") — useful for spotting tampering attempts.
        logger.warning("request rejected: %s", exc)
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    user = db.get(User, int(payload["sub"]))
    if user is None:
        logger.warning("token valid but user_id=%s no longer exists", payload.get("sub"))
        raise HTTPException(status_code=401, detail="user no longer exists")
    return user
