import json
import sqlite3
from pathlib import Path

CURRICULUM_DIR = Path(__file__).resolve().parent

FLAG_COLUMNS = {"blind75": "in_blind75", "neetcode150": "in_neetcode150"}


def load(name: str) -> list[str]:
    return json.loads((CURRICULUM_DIR / f"{name}.json").read_text())


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
