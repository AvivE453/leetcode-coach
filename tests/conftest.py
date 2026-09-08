"""Shared test setup. Test modules import CODE / TWO_SUM / seed_db from here.

pytest puts this directory on sys.path (there is no tests/__init__.py), so
`from conftest import ...` reaches the module pytest has already loaded.
"""

import sqlite3

import pytest

from coach import config, db

# The solution every suite logs: real Python, deliberately wrong, so a review
# fixture has something to find and the tagger has something to read.
CODE = "class Solution:\n    def twoSum(self, nums, target):\n        return []\n"

TWO_SUM = [
    {
        "number": 1,
        "slug": "two-sum",
        "title": "Two Sum",
        "difficulty": "Easy",
        "official_tags": '["array"]',
        "paid_only": 0,
    }
]


@pytest.fixture(autouse=True)
def no_api_key(monkeypatch):
    """Tests must never hit the real API: config.py loads .env at import,
    so strip the key from the environment for every test."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def seed_db(tmp_path, monkeypatch, problems=None) -> sqlite3.Connection:
    """A fresh database wired into config and seeded with a catalog, left open.

    Pointing config at tmp_path is what keeps a test off data/coach.db, so it is
    the same four lines everywhere and is worth having one copy of. Callers that
    run CLI commands or HTTP requests close the connection right away - those open
    their own through db.connect() - while callers that call service functions
    directly keep this one.
    """
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "coach.db")
    conn = db.connect()
    db.init_schema(conn)
    db.upsert_problems(conn, problems if problems is not None else TWO_SUM)
    return conn
