"""Phase 8.9: Settings.database_url must normalize the connection-string schemes
Render (and Heroku-style platforms generally) hand out — postgres:// and bare
postgresql:// — to the explicit postgresql+psycopg2:// scheme this app's
SQLAlchemy engine expects. See app/config.py's validator docstring for why."""
from app.config import Settings


def test_postgres_scheme_is_normalized():
    s = Settings(database_url="postgres://u:p@host:5432/db")
    assert s.database_url == "postgresql+psycopg2://u:p@host:5432/db"


def test_bare_postgresql_scheme_is_normalized():
    s = Settings(database_url="postgresql://u:p@host:5432/db")
    assert s.database_url == "postgresql+psycopg2://u:p@host:5432/db"


def test_explicit_driver_scheme_is_left_alone():
    s = Settings(database_url="postgresql+psycopg2://u:p@host:5432/db")
    assert s.database_url == "postgresql+psycopg2://u:p@host:5432/db"
