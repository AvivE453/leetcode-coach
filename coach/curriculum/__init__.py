import json
import sqlite3
from pathlib import Path

CURRICULUM_DIR = Path(__file__).resolve().parent

FLAG_COLUMNS = {"blind75": "in_blind75", "neetcode150": "in_neetcode150"}


def load(name: str) -> list[str]:
    return json.loads((CURRICULUM_DIR / f"{name}.json").read_text())


def progress(conn: sqlite3.Connection) -> dict[str, dict[str, int]]:
    """{"done": n, "total": n} per curriculum list.

    One definition of "how far along am I", shared by `coach stats` and the weekly
    analysis - they computed it with separate copies of this SQL. The named keys are
    the shape every consumer already wanted: all three web pages read .done/.total,
    so this is what /api/stats, /api/plan and the frozen weekly snapshot serve
    without reshaping it on the way out.
    """
    out = {}
    for name, column in FLAG_COLUMNS.items():
        total = conn.execute(f"SELECT COUNT(*) FROM problems WHERE {column} = 1").fetchone()[0]
        done = conn.execute(
            f"""
            SELECT COUNT(DISTINCT a.problem_number)
            FROM attempts a JOIN problems p ON p.number = a.problem_number
            WHERE p.{column} = 1
            """
        ).fetchone()[0]
        out[name] = {"done": done, "total": total}
    return out


def apply_flags(conn: sqlite3.Connection) -> dict[str, int]:
    flagged = {}
    for name, column in FLAG_COLUMNS.items():
        slugs = load(name)
        conn.execute(f"UPDATE problems SET {column} = 0")
        conn.executemany(
            f"UPDATE problems SET {column} = 1 WHERE slug = ?",
            [(slug,) for slug in slugs],
        )
        flagged[name] = conn.execute(
            f"SELECT COUNT(*) FROM problems WHERE {column} = 1"
        ).fetchone()[0]
    conn.commit()
    return flagged
