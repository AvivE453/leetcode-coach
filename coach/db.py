import sqlite3
from pathlib import Path

from coach import config

# Its own constant because merge_attempts_into_solutions() recreates the table from it.
SOLUTIONS_TABLE = """
CREATE TABLE IF NOT EXISTS solutions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    problem_number INTEGER NOT NULL REFERENCES problems(number),
    date TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('clean', 'struggled', 'hints', 'failed')),
    minutes INTEGER,
    note TEXT,
    code TEXT NOT NULL,
    due_when_logged INTEGER
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
    intended_secondary_patterns TEXT NOT NULL DEFAULT '[]',
    content TEXT
);

{SOLUTIONS_TABLE}
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
    merge_attempts_into_solutions(conn)
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(problems)")}
    if "intended_pattern" not in columns:
        conn.execute("ALTER TABLE problems ADD COLUMN intended_pattern TEXT")
    if "intended_secondary_patterns" not in columns:
        conn.execute(
            "ALTER TABLE problems ADD COLUMN intended_secondary_patterns TEXT NOT NULL DEFAULT '[]'"
        )
    if "content" not in columns:
        conn.execute("ALTER TABLE problems ADD COLUMN content TEXT")
    if not has_column(conn, "solutions", "due_when_logged"):
        conn.execute("ALTER TABLE solutions ADD COLUMN due_when_logged INTEGER")
    conn.commit()


def has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    return any(row["name"] == column for row in conn.execute(f"PRAGMA table_info({table})"))


def merge_attempts_into_solutions(conn: sqlite3.Connection) -> None:
    """Fold each attempt into the solution logged with it, leaving one row per solve.

    Logging always wrote the two together, so the split only cost every reader a join.
    Each solve keeps its solution's id, which enrichments, reviews and embeddings are
    keyed by, so none of them changes. It refuses unless attempts and solutions pair
    up exactly one-to-one on the same problem: this is the only copy of the history,
    and a row without a partner would silently vanish in the join.

    `solutions` is never renamed, unlike the usual rebuild. It is the table the others
    reference, and SQLite rewrites a renamed table's incoming REFERENCES to follow it -
    to the copy about to be dropped. So the rows are copied out, both tables dropped and
    `solutions` recreated under its own name, in one transaction: a failure part-way
    rolls back to the two tables as they were. Foreign keys are off meanwhile, because
    with them on SQLite refuses to drop a table other rows still point into.
    """
    if not conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'attempts'"
    ).fetchone():
        return
    attempts, solutions, paired = conn.execute(
        """
        SELECT (SELECT COUNT(*) FROM attempts),
               (SELECT COUNT(*) FROM solutions),
               (SELECT COUNT(DISTINCT a.id) FROM solutions s
                JOIN attempts a ON a.id = s.attempt_id AND a.problem_number = s.problem_number)
        """
    ).fetchone()
    if not attempts == solutions == paired:
        raise RuntimeError(
            f"{attempts} attempts and {solutions} solutions, of which {paired} pair up on the "
            "same problem: not one-to-one, so nothing was merged"
        )

    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.executescript(
            f"""
            BEGIN;
            CREATE TABLE solutions_merged AS
                SELECT s.id, a.problem_number, a.date, a.outcome, a.minutes, a.note, s.code
                FROM solutions s JOIN attempts a ON a.id = s.attempt_id;
            DROP TABLE solutions;
            DROP TABLE attempts;
            {SOLUTIONS_TABLE}
            INSERT INTO solutions (id, problem_number, date, outcome, minutes, note, code)
            SELECT id, problem_number, date, outcome, minutes, note, code FROM solutions_merged;
            DROP TABLE solutions_merged;
            COMMIT;
            """
        )
    except sqlite3.Error:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


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
