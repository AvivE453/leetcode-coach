import json
import sqlite3
from datetime import date, timedelta

WINDOW_DAYS = 7


def collect(conn: sqlite3.Connection, today: date) -> dict:
    """Everything that happened in the last 7 days, one row per attempt.

    Each attempt carries its main patterns as a list - empty when the solve was
    never tagged, which is still a solve, just one with nothing to attribute it to.
    """
    start = today - timedelta(days=WINDOW_DAYS - 1)
    rows = conn.execute(
        """
        SELECT a.date, a.problem_number, p.title, p.difficulty, a.outcome, a.minutes,
               en.main_patterns
        FROM attempts a
        JOIN problems p ON p.number = a.problem_number
        LEFT JOIN solutions s ON s.attempt_id = a.id
        LEFT JOIN enrichments en ON en.solution_id = s.id
        WHERE a.date >= ?
        ORDER BY a.date, a.id
        """,
        (start.isoformat(),),
    ).fetchall()
    attempts = [
        {**dict(r), "main_patterns": json.loads(r["main_patterns"]) if r["main_patterns"] else []}
        for r in rows
    ]
    return {
        "start": start,
        "end": today,
        "attempts": attempts,
        "distinct_problems": len({r["problem_number"] for r in attempts}),
    }
