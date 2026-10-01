"""Cross-user isolation for app/services/forecast.py's forecast_expenses, covering
the account_id scoping fix: like every other analytics function's _scope() helper
(app/services/analytics.py), a client-supplied account_id must only ever narrow
within the caller's own data, never let them see another user's forecast.

Needs a real PostgreSQL connection — forecast.py's _get_monthly_expenses uses
Postgres's to_char(), so this can't run against SQLite. Runs entirely inside a
disposable, uniquely-named schema (created and dropped by this test) on whatever
DATABASE_URL is configured — it never touches the application's own tables/data,
public schema included. Skips cleanly if no PostgreSQL is reachable at all.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db.database import Base
from app.models.account import Account
from app.models.enums import TransactionType
from app.models.transaction import Transaction
from app.models.user import User
from app.services.forecast import forecast_expenses


@pytest.fixture
def isolated_db_session():
    schema = f"pytest_forecast_{uuid.uuid4().hex[:10]}"
    admin_engine = create_engine(settings.database_url)
    try:
        with admin_engine.connect() as conn:
            conn.execute(text(f"CREATE SCHEMA {schema}"))
            conn.commit()
    except Exception as exc:
        pytest.skip(f"PostgreSQL not reachable, skipping DB-dependent isolation test: {exc}")
    admin_engine.dispose()

    scoped_engine = create_engine(
        settings.database_url, connect_args={"options": f"-csearch_path={schema}"}
    )
    Base.metadata.create_all(bind=scoped_engine)
    Session = sessionmaker(bind=scoped_engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        scoped_engine.dispose()
        cleanup_engine = create_engine(settings.database_url)
        with cleanup_engine.connect() as conn:
            conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
            conn.commit()
        cleanup_engine.dispose()


def _make_user_with_data(db, *, email: str, transaction_date: str, amount: str) -> tuple[User, Account]:
    user = User(email=email)
    db.add(user)
    db.flush()
    account = Account(user_id=user.id, name="Primary", currency="INR")
    db.add(account)
    db.flush()
    db.add(
        Transaction(
            user_id=user.id,
            account_id=account.id,
            transaction_date=date.fromisoformat(transaction_date),
            description_raw="TEST",
            amount=Decimal(amount),
            transaction_type=TransactionType.DEBIT,
            currency="INR",
            dedupe_hash=f"{email}-{transaction_date}-{amount}",
        )
    )
    db.commit()
    return user, account


def test_forecast_never_includes_another_users_data(isolated_db_session):
    db = isolated_db_session
    user_a, account_a = _make_user_with_data(
        db, email="fc-a@example.com", transaction_date="2026-01-01", amount="100"
    )
    user_b, account_b = _make_user_with_data(
        db, email="fc-b@example.com", transaction_date="2026-01-01", amount="999999"
    )

    result = forecast_expenses(db, user_id=user_a.id)
    assert result.historical_expenses == [Decimal("100.00")]
    assert Decimal("999999") not in result.historical_expenses


def test_foreign_account_id_yields_no_data_not_another_users_forecast(isolated_db_session):
    """The fix: passing someone else's account_id must behave like 'nothing found
    in my own data under that id' (insufficient_data), never leak that account's
    real owner's numbers — same contract as analytics.py's _scope()."""
    db = isolated_db_session
    user_a, account_a = _make_user_with_data(
        db, email="fc-a2@example.com", transaction_date="2026-01-01", amount="100"
    )
    user_b, account_b = _make_user_with_data(
        db, email="fc-b2@example.com", transaction_date="2026-01-01", amount="999999"
    )

    result = forecast_expenses(db, user_id=user_a.id, account_id=account_b.id)
    assert result.method == "insufficient_data"
    assert result.historical_expenses == []
    assert Decimal("999999") not in result.historical_expenses


def test_own_account_id_correctly_scopes_to_that_account(isolated_db_session):
    db = isolated_db_session
    user_a, account_a = _make_user_with_data(
        db, email="fc-a3@example.com", transaction_date="2026-01-01", amount="100"
    )

    result = forecast_expenses(db, user_id=user_a.id, account_id=account_a.id)
    assert result.historical_expenses == [Decimal("100.00")]
