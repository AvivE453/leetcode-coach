import sqlite3
from datetime import date, timedelta

from coach import curriculum, enrich

STALE_DAYS = 30
WEAK_MIN_ATTEMPTS = 2
WEAK_STRUGGLE_RATE = 0.5


def analyze(conn: sqlite3.Connection, today: date) -> dict:
    rows = conn.execute(
        """
        SELECT en.pattern,
               COUNT(*) AS attempts,
               SUM(a.outcome != 'clean') AS rough,
               MAX(a.date) AS last_date
        FROM attempts a
        JOIN solutions s ON s.attempt_id = a.id
        JOIN enrichments en ON en.solution_id = s.id
        GROUP BY en.pattern
        ORDER BY en.pattern
        """
    ).fetchall()
    patterns = [
        {
            "pattern": r["pattern"],
            "attempts": r["attempts"],
            "struggle_rate": r["rough"] / r["attempts"],
            "last_date": date.fromisoformat(r["last_date"]),
        }
        for r in rows
    ]
    weak = [
        p["pattern"]
        for p in sorted(patterns, key=lambda p: -p["struggle_rate"])
        if p["attempts"] >= WEAK_MIN_ATTEMPTS and p["struggle_rate"] >= WEAK_STRUGGLE_RATE
    ]
    stale = [
        p["pattern"] for p in patterns if p["last_date"] < today - timedelta(days=STALE_DAYS)
    ]

    due = conn.execute(
        """
        SELECT p.number, p.slug, p.title, p.difficulty, r.next_due
        FROM review_state r JOIN problems p ON p.number = r.problem_number
        WHERE r.next_due <= ?
        ORDER BY r.next_due
        """,
        ((today + timedelta(days=6)).isoformat(),),
    ).fetchall()

    progress = {}
    for name, column in curriculum.FLAG_COLUMNS.items():
        total = conn.execute(f"SELECT COUNT(*) FROM problems WHERE {column} = 1").fetchone()[0]
        done = conn.execute(
            f"""
            SELECT COUNT(DISTINCT a.problem_number)
            FROM attempts a JOIN problems p ON p.number = a.problem_number
            WHERE p.{column} = 1
            """
        ).fetchone()[0]
        progress[name] = (done, total)

    return {
        "patterns": patterns,
        "weak_patterns": weak,
        "stale_patterns": stale,
        "off_pattern": enrich.off_pattern_problems(conn),
        "due": due,
        "curriculum": progress,
    }
