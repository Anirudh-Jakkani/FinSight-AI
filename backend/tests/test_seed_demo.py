"""Covers app/db/seed_demo.py's constants and its bundled copy of the sample
dataset. Does not touch a database — the idempotency/pipeline behavior itself is
exercised manually against an isolated schema (see docs/render-deployment.md's
testing notes), not under pytest, since it needs a real PostgreSQL connection."""
from pathlib import Path

from app.db.seed_demo import DEMO_CSV_PATH


def test_bundled_csv_matches_repo_root_sample_dataset():
    """backend/app/db/seed_data/sample_transactions.csv must stay byte-identical to
    data/sample_transactions.csv — see seed_demo.py's module docstring for why a
    copy exists at all (Docker build context) instead of reading the original."""
    repo_root_csv = Path(__file__).resolve().parents[2] / "data" / "sample_transactions.csv"
    assert DEMO_CSV_PATH.read_bytes() == repo_root_csv.read_bytes()


def test_bundled_csv_is_the_verified_90_row_dataset():
    rows = DEMO_CSV_PATH.read_text().strip().splitlines()
    assert rows[0] == "date,description,amount,transaction_type"
    assert len(rows) - 1 == 90
