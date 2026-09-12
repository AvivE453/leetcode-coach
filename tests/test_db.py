import pytest
from conftest import tag_solution

from coach import db, mastery, review


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


def test_init_schema_drops_the_stored_weekly_runs_table(tmp_path):
    """The weekly review is recomputed on read now, so the frozen rows it used to
    be served from - and the LLM note stored beside them - have no reader left."""
    conn = db.connect(tmp_path / "test.db")
    conn.execute(
        """
        CREATE TABLE weekly_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_start TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            report_path TEXT,
            stats TEXT,
            degraded INTEGER NOT NULL DEFAULT 0,
            narrative TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO weekly_runs (week_start, generated_at) VALUES ('2026-08-24', '2026-08-30')"
    )

    db.init_schema(conn)
    db.init_schema(conn)  # and again on a database that never had the table

    tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "weekly_runs" not in tables
    # The solve history itself is untouched by the migration.
    assert "attempts" in tables and "solutions" in tables


def test_init_schema_drops_pattern_scores_and_keeps_the_history_it_came_from(tmp_path):
    """Mastery is computed from the saved history on every read now, so the table that
    cached it has no reader left - and dropping it must not touch anything else."""
    conn = db.connect(tmp_path / "test.db")
    db.init_schema(conn)
    conn.execute(
        """
        CREATE TABLE pattern_scores (
            pattern TEXT PRIMARY KEY,
            score REAL NOT NULL,
            attempts INTEGER NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute("INSERT INTO pattern_scores VALUES ('hashmap', 3.8, 1, '2026-09-01')")
    db.upsert_problems(conn, [make_problem()])
    conn.execute(
        "INSERT INTO attempts (id, problem_number, date, outcome) VALUES (1, 1, '2026-09-01', 'clean')"
    )
    conn.execute(
        """
        INSERT INTO solutions (id, problem_number, attempt_id, code, created_at)
        VALUES (1, 1, 1, 'code', '2026-09-01')
        """
    )
    tag_solution(conn, 1, "hashmap")
    review.save(
        conn,
        1,
        review.Review(
            strengths=[],
            issues=[review.Issue(category="bug", description="Off by one.")],
            time_complexity="O(n)",
            space_complexity="O(1)",
            optimal_time_complexity="O(n)",
            better_approach=None,
            verdict="needs-work",
        ),
    )
    conn.execute(
        """
        INSERT INTO review_state (problem_number, ease, interval_days, next_due)
        VALUES (1, 2.5, 7.0, '2026-09-08')
        """
    )
    conn.commit()
    history = ("problems", "attempts", "solutions", "enrichments", "reviews", "review_state")

    def snapshot():
        return {t: [tuple(r) for r in conn.execute(f"SELECT * FROM {t}")] for t in history}

    before = snapshot()

    db.init_schema(conn)
    db.init_schema(conn)  # and again, on a database that no longer has the table

    tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "pattern_scores" not in tables
    assert snapshot() == before
    # the score the cache held is still what the history says: 0.7*5 + 0.3*1
    assert mastery.pattern_stats(mastery.load_history(conn))[0]["score"] == pytest.approx(3.8)


def test_init_schema_rebuilds_single_pattern_enrichments_as_main_patterns(tmp_path):
    """A solve can have several main patterns now. SQLite before 3.35 cannot drop the old
    NOT NULL `pattern` column, so the table is rebuilt - and every row in it, and every
    table beside it, has to come through intact."""
    conn = db.connect(tmp_path / "test.db")
    db.init_schema(conn)
    conn.execute("DROP TABLE enrichments")
    conn.execute(
        """
        CREATE TABLE enrichments (
            solution_id INTEGER PRIMARY KEY REFERENCES solutions(id),
            pattern TEXT NOT NULL,
            secondary_patterns TEXT NOT NULL DEFAULT '[]',
            data_structures TEXT NOT NULL DEFAULT '[]',
            key_trick TEXT,
            time_complexity TEXT,
            space_complexity TEXT,
            model TEXT,
            prompt_version TEXT
        )
        """
    )
    db.upsert_problems(conn, [make_problem()])
    conn.execute(
        "INSERT INTO attempts (id, problem_number, date, outcome) VALUES (1, 1, '2026-09-01', 'clean')"
    )
    conn.execute(
        """
        INSERT INTO solutions (id, problem_number, attempt_id, code, created_at)
        VALUES (1, 1, 1, 'code', '2026-09-01')
        """
    )
    conn.execute(
        """
        INSERT INTO enrichments VALUES (1, 'dp-knapsack', '["dfs"]', '["list"]',
            'Count the ways per coin.', 'O(n*k)', 'O(k)', 'claude-sonnet-5', 'enrich-v3')
        """
    )
    conn.execute("INSERT INTO embeddings (solution_id, vector) VALUES (1, x'0000803f')")
    conn.commit()
    beside = ("problems", "attempts", "solutions", "embeddings")

    def snapshot():
        return {t: [tuple(r) for r in conn.execute(f"SELECT * FROM {t}")] for t in beside}

    before = snapshot()

    db.init_schema(conn)
    db.init_schema(conn)  # and again, on a table that is already rebuilt

    columns = {r["name"] for r in conn.execute("PRAGMA table_info(enrichments)")}
    assert "pattern" not in columns
    assert dict(conn.execute("SELECT * FROM enrichments").fetchone()) == {
        "solution_id": 1,
        "main_patterns": '["dp-knapsack"]',
        "secondary_patterns": '["dfs"]',
        "data_structures": '["list"]',
        "key_trick": "Count the ways per coin.",
        "time_complexity": "O(n*k)",
        "space_complexity": "O(k)",
        "model": "claude-sonnet-5",
        "prompt_version": "enrich-v3",
    }
    assert snapshot() == before
    tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert not any(t.startswith("enrichments_") for t in tables)


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
