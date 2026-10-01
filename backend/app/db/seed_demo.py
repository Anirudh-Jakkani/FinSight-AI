"""Idempotent demo-seed command for a production deployment (Render): creates the
existing demo user/account (locally: user id 2, phase22-test@example.com, account
"Test Checking") and imports the verified 90-row sample dataset into it — through
the exact same migrations -> ingestion -> merchant-cleaning -> rule/ML-categorization
pipeline a real upload goes through. Nothing here reimplements that logic: it's a
thin driver over already-tested services, same pattern as app/db/init_db.py and
app/services/pipeline.py's run_pipeline (Phase 5), which this calls directly.

Safe to run against any database, any number of times, without duplicating anything:
- Migrations: `alembic upgrade head` is a no-op once already current (Phase 8.7).
- The user/account lookup is by email/name — rerunning finds the existing rows
  instead of creating new ones.
- The data import goes through ingest_csv's existing dedupe_hash check (Phase 2.2),
  which already skips any row it's seen before for this user — rerunning imports 0
  new rows, same dataset back. Nothing is ever deleted or overwritten.
This is also why running it against this project's own local dev database (which
already has this exact user and dataset from earlier manual testing) is a safe
no-op rather than a duplicate — see backend/tests/test_seed_demo.py, which proves
exactly that by running it twice in a row against an isolated schema.

backend/app/db/seed_data/sample_transactions.csv is a byte-for-byte copy of the
repo-root data/sample_transactions.csv (not read from that path at runtime: the
Docker build context for this image is backend/, per backend/Dockerfile, which
does not include the repo-root data/ directory). test_seed_demo.py asserts the two
stay identical.

No secret is ever hardcoded here. DEMO_USER_PASSWORD is optional and read from the
environment only — if unset, the demo user is created with no password (same as any
user created before Phase 7.1: visible in the data, just not loggable-into until a
password is set). See docs/render-deployment.md.

Usage:
    python -m app.db.seed_demo
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.models.account import Account
from app.models.user import User
from app.services.auth import hash_password
from app.services.pipeline import run_pipeline
from app.services.transaction_ingestion import IngestionError

logger = logging.getLogger(__name__)

DEMO_EMAIL = "phase22-test@example.com"
DEMO_ACCOUNT_NAME = "Test Checking"
DEMO_CURRENCY = "INR"
DEMO_CSV_FILENAME = "sample_transactions.csv"
DEMO_CSV_PATH = Path(__file__).resolve().parent / "seed_data" / "sample_transactions.csv"


def _get_or_create_demo_user(db: Session) -> User:
    user = db.execute(select(User).where(User.email == DEMO_EMAIL)).scalar_one_or_none()
    if user is not None:
        return user

    password = os.environ.get("DEMO_USER_PASSWORD")  # optional, never hardcoded
    user = User(email=DEMO_EMAIL, hashed_password=hash_password(password) if password else None)
    db.add(user)
    db.flush()  # assigns user.id before the dependent account is created
    logger.info(
        "seed_demo: created demo user id=%s email=%s (password set: %s)",
        user.id, user.email, bool(password),
    )
    return user


def _get_or_create_demo_account(db: Session, user: User) -> Account:
    account = db.execute(
        select(Account).where(Account.user_id == user.id, Account.name == DEMO_ACCOUNT_NAME)
    ).scalar_one_or_none()
    if account is not None:
        return account

    account = Account(user_id=user.id, name=DEMO_ACCOUNT_NAME, currency=DEMO_CURRENCY)
    db.add(account)
    db.flush()
    logger.info("seed_demo: created demo account id=%s for user id=%s", account.id, user.id)
    return account


def seed_demo() -> None:
    # Phase 8.7: no-op once the database is already at head — safe to call here
    # unconditionally rather than assuming a prior deploy step already ran it.
    cfg = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    command.upgrade(cfg, "head")

    db = SessionLocal()
    try:
        user = _get_or_create_demo_user(db)
        account = _get_or_create_demo_account(db, user)
        db.commit()
        db.refresh(user)
        db.refresh(account)

        file_bytes = DEMO_CSV_PATH.read_bytes()
        try:
            result = run_pipeline(
                db,
                file_bytes=file_bytes,
                filename=DEMO_CSV_FILENAME,
                user_id=user.id,
                account_id=account.id,
                currency=DEMO_CURRENCY,
            )
        except IngestionError as exc:
            raise SystemExit(f"seed_demo: pipeline failed: {exc}") from exc

        print(f"Demo user:    id={user.id} email={user.email}")
        print(f"Demo account: id={account.id} name={account.name!r} currency={account.currency}")
        print(
            f"Ingestion:    {result.ingestion.rows_processed} rows processed, "
            f"{result.ingestion.inserted} inserted, "
            f"{result.ingestion.skipped_duplicates} already present (skipped), "
            f"{result.ingestion.failed} failed"
        )
        print(f"Cleaning:     {result.merchants_cleaned.updated} merchant(s) cleaned")
        print(f"Rules:        {result.rows_categorized} row(s) categorized")
        print(f"ML:           {result.ml_apply.message}")
    finally:
        db.close()


if __name__ == "__main__":
    seed_demo()
