from coach import db, review


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


def test_init_schema_migrates_pre_m11_problems_table(tmp_path):
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
            in_neetcode150 INTEGER NOT NULL DEFAULT 0,
            intended_pattern TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO problems (number, slug, title, difficulty, intended_pattern)
        VALUES (1, 'two-sum', 'Two Sum', 'Easy', 'hashmap')
        """
    )

    db.init_schema(conn)
    db.init_schema(conn)

    columns = {row["name"] for row in conn.execute("PRAGMA table_info(problems)")}
    assert "intended_secondary_patterns" in columns
    # An existing problem keeps its central pattern and starts with no alternates,
    # which it accrues the next time any of its solves is enriched.
    row = conn.execute("SELECT * FROM problems WHERE number = 1").fetchone()
    assert row["intended_pattern"] == "hashmap"
    assert row["intended_secondary_patterns"] == "[]"


def test_init_schema_migrates_pre_m9_weekly_runs_table(tmp_path):
    conn = db.connect(tmp_path / "test.db")
    conn.execute(
        """
        CREATE TABLE weekly_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_start TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            report_path TEXT,
            stats TEXT,
            degraded INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        "INSERT INTO weekly_runs (week_start, generated_at) VALUES ('2026-08-24', '2026-08-30')"
    )

    db.init_schema(conn)
    db.init_schema(conn)

    columns = {row["name"] for row in conn.execute("PRAGMA table_info(weekly_runs)")}
    assert "narrative" in columns
    # The pre-migration run survives, with no note attached.
    row = conn.execute("SELECT * FROM weekly_runs").fetchone()
    assert row["week_start"] == "2026-08-24"
    assert row["narrative"] is None


def test_reviews_round_trip_through_the_store(tmp_path):
    """A stored review must come back as the same Review, JSON list fields included."""
    conn = db.connect(tmp_path / "test.db")
    db.init_schema(conn)
    db.upsert_problems(conn, [make_problem()])
    conn.execute(
        "INSERT INTO solutions (id, problem_number, code, created_at) VALUES (1, 1, 'code', '2026-09-01')"
    )

    assert review.load(conn, 1) is None

    r = review.Review(
        strengths=["Single pass.", "Handles duplicates."],
        issues=[review.Issue(category="edge-case", description="Breaks on an empty list.")],
        time_complexity="O(n)",
        space_complexity="O(n)",
        optimal_time_complexity="O(n)",
        better_approach=None,
        verdict="acceptable",
    )
    review.save(conn, 1, r)
    conn.commit()

    assert review.load(conn, 1) == r

    stored = conn.execute("SELECT * FROM reviews WHERE solution_id = 1").fetchone()
    assert stored["prompt_version"] == review.PROMPT_VERSION
    assert stored["model"]


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
