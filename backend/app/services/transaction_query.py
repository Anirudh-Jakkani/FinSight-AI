"""Read/delete operations on stored transactions (Phase 2.4). Pure query-building and
persistence; HTTP concerns (status codes, query-param parsing) stay in app/api."""
from __future__ import annotations

from datetime import date

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models.enums import TransactionType
from app.models.transaction import Transaction


def _apply_filters(
    stmt: Select,
    *,
    user_id: int,
    account_id: int | None,
    category: str | None,
    transaction_type: TransactionType | None,
    needs_review: bool | None,
    date_from: date | None,
    date_to: date | None,
) -> Select:
    stmt = stmt.where(Transaction.user_id == user_id)
    if account_id is not None:
        stmt = stmt.where(Transaction.account_id == account_id)
    if category is not None:
        stmt = stmt.where(func.lower(Transaction.category) == category.lower())
    if transaction_type is not None:
        stmt = stmt.where(Transaction.transaction_type == transaction_type)
    if needs_review is not None:
        stmt = stmt.where(Transaction.needs_review == needs_review)
    if date_from is not None:
        stmt = stmt.where(Transaction.transaction_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(Transaction.transaction_date <= date_to)
    return stmt


def list_transactions(
    db: Session,
    *,
    user_id: int,
    account_id: int | None = None,
    category: str | None = None,
    transaction_type: TransactionType | None = None,
    needs_review: bool | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Transaction], int]:
    filter_kwargs = dict(
        user_id=user_id,
        account_id=account_id,
        category=category,
        transaction_type=transaction_type,
        needs_review=needs_review,
        date_from=date_from,
        date_to=date_to,
    )

    total = db.scalar(_apply_filters(select(func.count()).select_from(Transaction), **filter_kwargs))

    items = (
        db.execute(
            _apply_filters(select(Transaction), **filter_kwargs)
            .order_by(Transaction.transaction_date.desc(), Transaction.id.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )

    return list(items), total or 0


def get_transaction(db: Session, *, transaction_id: int, user_id: int) -> Transaction | None:
    return db.execute(
        select(Transaction).where(Transaction.id == transaction_id, Transaction.user_id == user_id)
    ).scalar_one_or_none()


def delete_transaction(db: Session, *, transaction_id: int, user_id: int) -> bool:
    txn = get_transaction(db, transaction_id=transaction_id, user_id=user_id)
    if txn is None:
        return False
    db.delete(txn)
    db.commit()
    return True
