import sqlite3
from pathlib import Path

from coach import config

# Its own constant because rebuild_single_pattern_enrichments() recreates the table from it.
ENRICHMENTS_TABLE = """
CREATE TABLE IF NOT EXISTS enrichments (
    solution_id INTEGER PRIMARY KEY REFERENCES solutions(id),
    main_patterns TEXT NOT NULL,
    secondary_patterns TEXT NOT NULL DEFAULT '[]',
    data_structures TEXT NOT NULL DEFAULT '[]',
    key_trick TEXT,
    time_complexity TEXT,
    space_complexity TEXT,
    model TEXT,
    prompt_version TEXT
);
"""

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS problems (
    number INTEGER PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    difficulty TEXT NOT NULL,
    official_tags TEXT NOT NULL DEFAULT '[]',
    paid_only INTEGER NOT NULL DEFAULT 0,
    in_blind75 INTEGER NOT NULL DEFAULT 0,
    in_neetcode150 INTEGER NOT NULL DEFAULT 0,
    intended_pattern TEXT,
    intended_secondary_patterns TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    problem_number INTEGER NOT NULL REFERENCES problems(number),
    date TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('clean', 'struggled', 'hints', 'failed')),
    minutes INTEGER,
    note TEXT
);

CREATE TABLE IF NOT EXISTS solutions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    problem_number INTEGER NOT NULL REFERENCES problems(number),
    attempt_id INTEGER REFERENCES attempts(id),
    code TEXT NOT NULL,
    created_at TEXT NOT NULL
);

{ENRICHMENTS_TABLE}
CREATE TABLE IF NOT EXISTS reviews (
    solution_id INTEGER PRIMARY KEY REFERENCES solutions(id),
    verdict TEXT NOT NULL,
    strengths TEXT NOT NULL DEFAULT '[]',
    issues TEXT NOT NULL DEFAULT '[]',
    time_complexity TEXT,
    space_complexity TEXT,
    optimal_time_complexity TEXT,
    better_approach TEXT,
    created_at TEXT NOT NULL,
    model TEXT,
    prompt_version TEXT
);

CREATE TABLE IF NOT EXISTS embeddings (
    solution_id INTEGER PRIMARY KEY REFERENCES solutions(id),
    vector BLOB NOT NULL
);

CREATE TABLE IF NOT EXISTS review_state (
    problem_number INTEGER PRIMARY KEY REFERENCES problems(number),
    ease REAL NOT NULL,
    interval_days REAL NOT NULL,
    next_due TEXT NOT NULL,
    reps INTEGER NOT NULL DEFAULT 0,
    lapses INTEGER NOT NULL DEFAULT 0
);
"""


def connect(path: Path | None = None) -> sqlite3.Connection:
    if path is None:
        path = config.DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    rebuild_single_pattern_enrichments(conn)
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(problems)")}
    if "intended_pattern" not in columns:
        conn.execute("ALTER TABLE problems ADD COLUMN intended_pattern TEXT")
    if "intended_secondary_patterns" not in columns:
        conn.execute(
            "ALTER TABLE problems ADD COLUMN intended_secondary_patterns TEXT NOT NULL DEFAULT '[]'"
        )
    # The weekly review is recomputed on every read now, so the rows that froze one
    # week's numbers (and the LLM note beside them) have no reader left.
    conn.execute("DROP TABLE IF EXISTS weekly_runs")
    # Mastery is computed from the saved history on every read, so the table that
    # cached it has no reader left.
    conn.execute("DROP TABLE IF EXISTS pattern_scores")
    conn.commit()


def rebuild_single_pattern_enrichments(conn: sqlite3.Connection) -> None:
    """Carry enrichments tagged with one `pattern` over to a `main_patterns` list.

    A solve can have several main patterns now. SQLite before 3.35 cannot drop a
    column, and the old one was NOT NULL - every writer would have had to keep
    filling it - so the table is rebuilt instead, in one transaction: a failure
    part-way rolls back to the old table exactly as it was.
    """
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(enrichments)")}
    if "pattern" not in columns:
        return
    try:
        conn.executescript(
            f"""
            BEGIN;
            ALTER TABLE enrichments RENAME TO enrichments_single_pattern;
            {ENRICHMENTS_TABLE}
            INSERT INTO enrichments
                (solution_id, main_patterns, secondary_patterns, data_structures,
                 key_trick, time_complexity, space_complexity, model, prompt_version)
            SELECT solution_id, json_array(pattern), secondary_patterns, data_structures,
                   key_trick, time_complexity, space_complexity, model, prompt_version
            FROM enrichments_single_pattern;
            DROP TABLE enrichments_single_pattern;
            COMMIT;
            """
        )
    except sqlite3.Error:
        conn.rollback()
        raise


def upsert_problems(conn: sqlite3.Connection, problems: list[dict]) -> None:
    conn.executemany(
        """
        INSERT INTO problems (number, slug, title, difficulty, official_tags, paid_only)
        VALUES (:number, :slug, :title, :difficulty, :official_tags, :paid_only)
        ON CONFLICT(number) DO UPDATE SET
            slug = excluded.slug,
            title = excluded.title,
            difficulty = excluded.difficulty,
            official_tags = excluded.official_tags,
            paid_only = excluded.paid_only
        """,
        problems,
    )
    conn.commit()
