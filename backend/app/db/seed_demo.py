"""Idempotent demo-seed command for a production deployment (Render): creates the
existing demo user/account (locally: user id 2, phase22-test@example.com, account
"Test Checking") and imports the verified 90-row sample dataset into it — through
the exact same migrations -> ingestion -> merchant-cleaning -> rule-categorization ->
ML-categorization steps a real upload goes through (app/services/pipeline.py's
run_pipeline, Phase 5, sequences these same four calls; this calls each of them
directly instead of going through that wrapper, solely so a missing ML model can be
trained at the right point in between rule-categorization and ML-categorization —
see seed_demo()). Nothing here reimplements any of that logic: every step is the
same already-tested service function the API routes and run_pipeline itself call.

If app/ml/models/category_classifier.joblib doesn't exist yet (a fresh deployment:
that file is never committed — see .gitignore/.dockerignore — and is only ever
produced by training), this trains it via app/ml/train.py's train_classifier
(Phase 4.4, the same function POST /api/v1/ml/train calls — global, not scoped to
the demo user, exactly like that endpoint) on whatever labeled transactions already
exist at that point, which after rule-categorization includes the demo dataset.
Training only ever reads transactions and writes the model file — "nothing here
writes back to the transactions table" per that module's own docstring — so this
cannot modify transaction data. Once trained, a rerun finds the file already exists
and skips straight to using it, same as the fresh-deploy case always did from the
second run onward.

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
from app.ml.train import MODEL_PATH, train_classifier
from app.models.account import Account
from app.models.user import User
from app.services.auth import hash_password
from app.services.categorization import categorize_transactions
from app.services.cleaning import clean_merchants
from app.services.ml_categorization import apply_ml_categorization
from app.services.transaction_ingestion import IngestionError, ingest_csv

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
            ingestion = ingest_csv(
                db,
                file_bytes=file_bytes,
                filename=DEMO_CSV_FILENAME,
                user_id=user.id,
                account_id=account.id,
                currency=DEMO_CURRENCY,
            )
        except IngestionError as exc:
            raise SystemExit(f"seed_demo: pipeline failed: {exc}") from exc

        merchants_cleaned = clean_merchants(db, user_id=user.id)
        rows_categorized = categorize_transactions(db, user_id=user.id)

        # Train only if there's no model yet — a rerun finds the file already
        # exists and skips straight to applying it, same as any other idempotent
        # step here. See module docstring for why this can't modify transactions.
        if not MODEL_PATH.exists():
            training = train_classifier(db)
            print(f"ML training:  {training.message}")

        ml_apply = apply_ml_categorization(db, user_id=user.id)

        print(f"Demo user:    id={user.id} email={user.email}")
        print(f"Demo account: id={account.id} name={account.name!r} currency={account.currency}")
        print(
            f"Ingestion:    {ingestion.rows_processed} rows processed, "
            f"{ingestion.inserted} inserted, "
            f"{ingestion.skipped_duplicates} already present (skipped), "
            f"{ingestion.failed} failed"
        )
        print(f"Cleaning:     {merchants_cleaned.updated} merchant(s) cleaned")
        print(f"Rules:        {rows_categorized} row(s) categorized")
        print(f"ML:           {ml_apply.message}")
    finally:
        db.close()


if __name__ == "__main__":
    seed_demo()
