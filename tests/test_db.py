import sqlite3

import pytest
from conftest import store_solution

from coach import db, history, review


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


def test_reviews_round_trip_through_the_store(tmp_path):
    """A stored review must come back as the same Review, JSON list fields included."""
    conn = db.connect(tmp_path / "test.db")
    db.init_schema(conn)
    db.upsert_problems(conn, [make_problem()])
    solution_id = store_solution(conn, 1)

    assert review.load(conn, solution_id) is None

    r = review.Review(
        strengths=["Single pass.", "Handles duplicates."],
        issues=[review.Issue(category="edge-case", description="Breaks on an empty list.")],
        time_complexity="O(n)",
        space_complexity="O(n)",
        optimal_time_complexity="O(n)",
        better_approach=None,
        verdict="acceptable",
    )
    review.save(conn, solution_id, r)
    conn.commit()

    assert review.load(conn, solution_id) == r

    stored = conn.execute("SELECT * FROM reviews WHERE solution_id = ?", (solution_id,)).fetchone()
    assert stored["prompt_version"] == review.PROMPT_VERSION
    assert stored["model"]


def test_solution_outcome_is_constrained(tmp_path):
    conn = db.connect(tmp_path / "test.db")
    db.init_schema(conn)
    db.upsert_problems(conn, [make_problem()])

    store_solution(conn, 1, outcome="clean")
    with pytest.raises(sqlite3.IntegrityError):
        store_solution(conn, 1, outcome="easy")


def test_a_new_database_keeps_one_row_per_solve(tmp_path):
    conn = db.connect(tmp_path / "test.db")
    db.init_schema(conn)

    assert not table_exists(conn, "attempts")
    assert columns_of(conn, "solutions") == MERGED_COLUMNS


# The two tables every solve used to be split across, as data/coach.db still had them.
# `file_path` was never in SCHEMA: the retired solutions/ mirror left it in the real one.
SPLIT_TABLES = """
CREATE TABLE attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    problem_number INTEGER NOT NULL REFERENCES problems(number),
    date TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('clean', 'struggled', 'hints', 'failed')),
    minutes INTEGER,
    note TEXT
);
CREATE TABLE solutions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    problem_number INTEGER NOT NULL REFERENCES problems(number),
    attempt_id INTEGER REFERENCES attempts(id),
    code TEXT NOT NULL,
    created_at TEXT NOT NULL,
    file_path TEXT
);
"""

MERGED_COLUMNS = ["id", "problem_number", "date", "outcome", "minutes", "note", "code"]


def table_exists(conn, name) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
    ).fetchone() is not None


def columns_of(conn, table) -> list[str]:
    return [row["name"] for row in conn.execute(f"PRAGMA table_info({table})")]


def split_db(tmp_path, attempts, solutions):
    """A database from before the merge, holding exactly the rows given.

    SCHEMA runs after the split tables exist, so it adds every other table and leaves
    the old `solutions` alone - the shape `coach init` meets on a database that has not
    been through the merge. `attempts` rows are (id, problem, date, outcome, minutes, note);
    `solutions` rows are (id, problem, attempt_id, code, created_at, file_path).
    """
    conn = db.connect(tmp_path / "test.db")
    conn.executescript(SPLIT_TABLES)
    conn.executescript(db.SCHEMA)
    db.upsert_problems(conn, [make_problem(), make_problem(number=15, slug="3sum", title="3Sum")])
    conn.executemany("INSERT INTO attempts VALUES (?, ?, ?, ?, ?, ?)", attempts)
    conn.executemany("INSERT INTO solutions VALUES (?, ?, ?, ?, ?, ?)", solutions)
    conn.commit()
    return conn


def test_init_schema_merges_each_attempt_into_its_solution(tmp_path):
    """Each solve keeps its solution's id - not its attempt's - because enrichments,
    reviews and embeddings are keyed by it. The ids differ here so a merge that paired
    rows by id instead of by attempt_id would show."""
    conn = split_db(
        tmp_path,
        attempts=[
            (1, 1, "2026-09-01", "struggled", 25, "off by one"),
            (2, 15, "2026-09-02", "clean", None, None),
        ],
        solutions=[
            (7, 15, 2, "b", "2026-09-02", "solutions/0015-3sum.py"),
            (8, 1, 1, "a", "2026-09-01", None),
        ],
    )
    conn.execute(
        "INSERT INTO enrichments (solution_id, main_patterns) VALUES (7, '[\"two-pointers\"]')"
    )
    conn.execute(
        "INSERT INTO reviews (solution_id, verdict, created_at) VALUES (8, 'needs-work', '2026-09-01')"
    )
    conn.execute("INSERT INTO embeddings (solution_id, vector) VALUES (7, x'00')")
    conn.commit()

    db.init_schema(conn)
    db.init_schema(conn)

    assert not table_exists(conn, "attempts")
    assert columns_of(conn, "solutions") == MERGED_COLUMNS
    assert [tuple(row) for row in conn.execute("SELECT * FROM solutions ORDER BY id")] == [
        (7, 15, "2026-09-02", "clean", None, None, "b"),
        (8, 1, "2026-09-01", "struggled", 25, "off by one", "a"),
    ]
    # Every child row still names its solve, and the one reader of history sees them joined.
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert [(a.id, a.problem.number, a.main_patterns, a.verdict) for a in history.load(conn)] == [
        (8, 1, None, "needs-work"),
        (7, 15, ("two-pointers",), None),
    ]
    assert [row["solution_id"] for row in conn.execute("SELECT solution_id FROM embeddings")] == [7]


ATTEMPT_1 = (1, 1, "2026-09-01", "clean", None, None)
ATTEMPT_2 = (2, 1, "2026-09-02", "clean", None, None)


@pytest.mark.parametrize(
    ("attempts", "solutions"),
    [
        ([ATTEMPT_1, ATTEMPT_2], [(7, 1, 1, "a", "2026-09-01", None)]),
        ([ATTEMPT_1], [(7, 1, 1, "a", "2026-09-01", None), (8, 1, None, "b", "2026-09-01", None)]),
        ([ATTEMPT_1], [(7, 1, 1, "a", "2026-09-01", None), (8, 1, 1, "b", "2026-09-01", None)]),
        ([ATTEMPT_1], [(7, 15, 1, "a", "2026-09-01", None)]),
    ],
    ids=["attempt-without-solution", "solution-without-attempt", "two-solutions-one-attempt",
         "pair-across-problems"],
)
def test_init_schema_refuses_to_merge_rows_without_a_partner(tmp_path, attempts, solutions):
    """The merge is an inner join over the only copy of the history, so a row with no
    partner - or a partner on another problem - would vanish. It stops instead, and
    leaves both tables as they were."""
    conn = split_db(tmp_path, attempts, solutions)

    with pytest.raises(RuntimeError, match="not one-to-one"):
        db.init_schema(conn)

    assert conn.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == len(attempts)
    assert conn.execute("SELECT COUNT(*) FROM solutions").fetchone()[0] == len(solutions)
    assert "attempt_id" in columns_of(conn, "solutions")
