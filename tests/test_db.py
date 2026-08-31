from coach import db


def make_problem(**overrides) -> dict:
    problem = {
        "number": 1,
        "slug": "two-sum",
        "title": "Two Sum",
        "difficulty": "Easy",
        "official_tags": '["array", "hash-table"]',
        "paid_only": 0,
    }
    return problem | overrides


def test_schema_is_idempotent(tmp_path):
    conn = db.connect(tmp_path / "test.db")
    db.init_schema(conn)
    db.init_schema(conn)


def test_upsert_inserts_and_updates(tmp_path):
    conn = db.connect(tmp_path / "test.db")
    db.init_schema(conn)

    db.upsert_problems(conn, [make_problem()])
    row = conn.execute("SELECT * FROM problems WHERE number = 1").fetchone()
    assert row["slug"] == "two-sum"
    assert row["difficulty"] == "Easy"

    db.upsert_problems(conn, [make_problem(title="Two Sum (updated)")])
    assert conn.execute("SELECT COUNT(*) FROM problems").fetchone()[0] == 1
    row = conn.execute("SELECT * FROM problems WHERE number = 1").fetchone()
    assert row["title"] == "Two Sum (updated)"


def test_init_schema_migrates_pre_m2_problems_table(tmp_path):
    conn = db.connect(tmp_path / "test.db")
    conn.execute(
        """
        CREATE TABLE problems (
            number INTEGER PRIMARY KEY,
            slug TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            difficulty TEXT NOT NULL,
            official_tags TEXT NOT NULL DEFAULT '[]',
            paid_only INTEGER NOT NULL DEFAULT 0,
            in_blind75 INTEGER NOT NULL DEFAULT 0,
            in_neetcode150 INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    db.init_schema(conn)
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(problems)")}
    assert "intended_pattern" in columns


def test_attempt_outcome_is_constrained(tmp_path):
    import sqlite3

    import pytest

    conn = db.connect(tmp_path / "test.db")
    db.init_schema(conn)
    db.upsert_problems(conn, [make_problem()])

    conn.execute(
        "INSERT INTO attempts (problem_number, date, outcome) VALUES (1, '2026-08-31', 'clean')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO attempts (problem_number, date, outcome) VALUES (1, '2026-08-31', 'easy')"
        )
