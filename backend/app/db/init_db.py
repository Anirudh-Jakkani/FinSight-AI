"""Database initialization: applies all Alembic migrations up to the latest ("head").

Phase 8.7: this used to call SQLAlchemy's Base.metadata.create_all(), which issues
CREATE TABLE for missing tables but has no way to express an *alter* (new column,
changed constraint, etc.) on a table that already exists — every schema change had
to be applied by hand against every database (dev, anyone else's machine, prod).
Alembic's upgrade head applies whatever migrations a database is missing, in order,
starting from wherever that database currently is, so this remains safe to run
repeatedly against a fresh database or one already partway up to date.

Usage:
    python -m app.db.init_db
"""
from pathlib import Path

from alembic import command
from alembic.config import Config


def init_db() -> None:
    cfg = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    command.upgrade(cfg, "head")


if __name__ == "__main__":
    init_db()
    print("Database migrated to head.")
