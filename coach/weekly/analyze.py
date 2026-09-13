import sqlite3
from collections.abc import Sequence
from datetime import date, timedelta

from coach import assessment, corrections, curriculum, mastery, scheduler

STALE_DAYS = 30
# How far ahead a plan counts a review as due. The weekly plan covers the next
# seven days, so it pulls in everything through today+6; a daily plan passes 0,
# because solving a review early re-anchors SM-2 from today and shortens it.
PLAN_LOOKAHEAD_DAYS = 6


def analyze(
    conn: sqlite3.Connection,
    today: date,
    lookahead_days: int = PLAN_LOOKAHEAD_DAYS,
    history: Sequence[mastery.ScoredAttempt] | None = None,
) -> dict:
    # A caller that has already loaded mastery's history passes it in, so one
    # request reads it once - the weekly review needs it again for its baseline.
    if history is None:
        history = mastery.load_history(conn)
    patterns = mastery.pattern_stats(history)
    # Weak is the mastery score, not the raw struggle rate: five shaky-but-solved
    # attempts and five failures are the same rate and very different problems.
    # struggle_rate stays as the honest raw number the reports show.
    weak = [
        p["pattern"]
        for p in sorted(patterns, key=lambda p: p["score"])
        if mastery.is_weak(p["score"], p["attempts"])
    ]
    stale = [
        p["pattern"] for p in patterns if p["last_date"] < today - timedelta(days=STALE_DAYS)
    ]
    # Approach practice keeps the reviews' horizon: what is owed by it goes on the list, and
    # the rest waits for its date rather than coming back early for being unresolved.
    horizon = today + timedelta(days=lookahead_days)
    owed = corrections.outstanding(conn)

    return {
        "patterns": patterns,
        "weak_patterns": weak,
        "stale_patterns": stale,
        "corrections_due": [c for c in owed if c.due <= horizon],
        "corrections_upcoming": [c for c in owed if c.due > horizon],
        "due": scheduler.due_reviews(conn, today, lookahead_days),
        # Why a due problem came back, when its last practice day holds a reported failure.
        "findings": assessment.open_findings(conn),
        "curriculum": curriculum.progress(conn),
    }
