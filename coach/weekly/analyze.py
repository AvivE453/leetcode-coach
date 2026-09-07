import sqlite3
from datetime import date, timedelta

from coach import curriculum, enrich, mastery, scheduler

STALE_DAYS = 30
# How far ahead a plan counts a review as due. The weekly plan covers the next
# seven days, so it pulls in everything through today+6; a daily plan passes 0,
# because solving a review early re-anchors SM-2 from today and shortens it.
PLAN_LOOKAHEAD_DAYS = 6


def analyze(
    conn: sqlite3.Connection, today: date, lookahead_days: int = PLAN_LOOKAHEAD_DAYS
) -> dict:
    patterns = mastery.pattern_stats(conn)
    # Weak is the mastery score, not the raw struggle rate: five shaky-but-solved
    # attempts and five failures are the same rate and very different problems.
    # struggle_rate stays as the honest raw number the reports show.
    weak = [
        p["pattern"]
        for p in sorted(patterns, key=lambda p: p["score"] if p["score"] is not None else 5.0)
        if mastery.is_weak(p["score"], p["attempts"])
    ]
    stale = [
        p["pattern"] for p in patterns if p["last_date"] < today - timedelta(days=STALE_DAYS)
    ]

    return {
        "patterns": patterns,
        "weak_patterns": weak,
        "stale_patterns": stale,
        "off_pattern": enrich.off_pattern_problems(conn),
        "due": scheduler.due_reviews(conn, today, lookahead_days),
        "curriculum": curriculum.progress(conn),
    }
