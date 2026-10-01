"""CSV transaction ingestion: parse, validate, normalize, dedupe, and persist rows.

No categorization/ML happens here (later phases). Every inserted row is left with
category=None and needs_review=True so a future categorizer can pick it up.
"""
from __future__ import annotations

import hashlib
import io
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import pandas as pd
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.enums import TransactionType
from app.models.transaction import Transaction
from app.models.user import User

REQUIRED_COLUMNS = {"date", "description", "amount", "transaction_type"}
_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y")
_WHITESPACE_RE = re.compile(r"\s+")

logger = logging.getLogger(__name__)


@dataclass
class RowError:
    row_number: int
    raw: dict
    error: str


@dataclass
class IngestResult:
    rows_processed: int = 0
    inserted: int = 0
    skipped_duplicates: int = 0
    failed: int = 0
    errors: list[RowError] = field(default_factory=list)
    inserted_ids: list[int] = field(default_factory=list)


class IngestionError(Exception):
    """Request-level problem (bad file, bad header, unknown user/account) — not a row issue."""


def _parse_date(raw: str) -> date:
    raw = raw.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unrecognized date format: {raw!r}")


def _parse_amount(raw: str) -> Decimal:
    cleaned = raw.strip().replace(",", "").replace("₹", "").replace("$", "")
    if not cleaned:
        raise ValueError("amount is empty")
    try:
        amount = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"invalid amount: {raw!r}") from exc
    if amount <= 0:
        raise ValueError(f"amount must be positive: {raw!r}")
    return amount.quantize(Decimal("0.01"))


def _parse_transaction_type(raw: str) -> TransactionType:
    normalized = raw.strip().upper()
    try:
        return TransactionType(normalized)
    except ValueError as exc:
        raise ValueError(f"transaction_type must be CREDIT or DEBIT, got {raw!r}") from exc


def _clean_description(raw: str) -> str:
    return _WHITESPACE_RE.sub(" ", raw.strip()).upper()


def _dedupe_hash(transaction_date: date, amount: Decimal, description_raw: str, account_id: int) -> str:
    # docs/database-schema.md: dedupe_hash = hash(date, amount, raw description, account)
    payload = f"{transaction_date.isoformat()}|{amount}|{description_raw}|{account_id}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def ingest_csv(
    db: Session,
    *,
    file_bytes: bytes,
    filename: str,
    user_id: int,
    account_id: int,
    currency: str,
) -> IngestResult:
    user = db.get(User, user_id)
    if user is None:
        raise IngestionError(f"user_id {user_id} does not exist")

    account = db.get(Account, account_id)
    if account is None:
        raise IngestionError(f"account_id {account_id} does not exist")
    if account.user_id != user_id:
        raise IngestionError(f"account {account_id} does not belong to user {user_id}")

    try:
        frame = pd.read_csv(io.BytesIO(file_bytes), dtype=str, keep_default_na=False)
    except Exception as exc:
        raise IngestionError(f"could not parse CSV: {exc}") from exc

    frame.columns = [c.strip().lower() for c in frame.columns]
    missing = REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        raise IngestionError(f"CSV is missing required columns: {sorted(missing)}")

    result = IngestResult()
    seen_hashes: set[str] = set()
    to_insert: list[Transaction] = []

    for idx, row in frame.iterrows():
        row_number = idx + 2  # header is physical row 1; pandas rows are 0-indexed
        result.rows_processed += 1
        raw = row.to_dict()

        try:
            transaction_date = _parse_date(raw["date"])
            description_raw = raw["description"]
            if not description_raw.strip():
                raise ValueError("description is empty")
            amount = _parse_amount(raw["amount"])
            transaction_type = _parse_transaction_type(raw["transaction_type"])
        except ValueError as exc:
            result.failed += 1
            result.errors.append(RowError(row_number=row_number, raw=raw, error=str(exc)))
            continue

        dedupe_hash = _dedupe_hash(transaction_date, amount, description_raw, account_id)

        if dedupe_hash in seen_hashes:
            result.skipped_duplicates += 1
            continue
        seen_hashes.add(dedupe_hash)

        to_insert.append(
            Transaction(
                user_id=user_id,
                account_id=account_id,
                transaction_date=transaction_date,
                description_raw=description_raw,
                description_clean=_clean_description(description_raw),
                merchant=None,
                amount=amount,
                transaction_type=transaction_type,
                category=None,
                category_confidence=None,
                category_source=None,
                needs_review=True,
                currency=currency,
                source_file=filename,
                dedupe_hash=dedupe_hash,
            )
        )

    if to_insert:
        existing_hashes = {
            h
            for (h,) in db.query(Transaction.dedupe_hash).filter(
                Transaction.user_id == user_id,
                Transaction.dedupe_hash.in_([t.dedupe_hash for t in to_insert]),
            )
        }

        final_batch = [t for t in to_insert if t.dedupe_hash not in existing_hashes]
        result.skipped_duplicates += len(to_insert) - len(final_batch)

        if final_batch:
            db.add_all(final_batch)
            db.commit()
            for txn in final_batch:
                db.refresh(txn)
            result.inserted = len(final_batch)
            result.inserted_ids = [t.id for t in final_batch]

    logger.info(
        "ingest_csv user_id=%s account_id=%s filename=%s rows=%s inserted=%s skipped=%s failed=%s",
        user_id, account_id, filename, result.rows_processed,
        result.inserted, result.skipped_duplicates, result.failed,
    )
    return result
