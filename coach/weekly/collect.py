import sqlite3
from datetime import date, timedelta

WINDOW_DAYS = 7


def collect(conn: sqlite3.Connection, today: date) -> dict:
    """Everything that happened in the last 7 days, one row per attempt."""
    start = today - timedelta(days=WINDOW_DAYS - 1)
    attempts = conn.execute(
        """
        SELECT a.date, a.problem_number, p.title, p.difficulty, a.outcome, a.minutes,
               en.pattern, rv.verdict AS review_verdict, rv.issues AS review_issues
        FROM attempts a
        JOIN problems p ON p.number = a.problem_number
        LEFT JOIN solutions s ON s.attempt_id = a.id
        LEFT JOIN enrichments en ON en.solution_id = s.id
        LEFT JOIN reviews rv ON rv.solution_id = s.id
        WHERE a.date >= ?
        ORDER BY a.date, a.id
        """,
        (start.isoformat(),),
    ).fetchall()
    return {
        "start": start,
        "end": today,
        "attempts": attempts,
        "distinct_problems": len({r["problem_number"] for r in attempts}),
    }
