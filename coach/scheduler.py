import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta

QUALITY = {"clean": 5, "struggled": 3, "hints": 2, "failed": 1}
INITIAL_EASE = 2.5
MIN_EASE = 1.3
FIRST_INTERVAL = 7.0
SECOND_INTERVAL = 14.0
LAPSE_INTERVAL = 3.0
MAX_INTERVAL = 180.0


@dataclass(frozen=True)
class ReviewState:
    ease: float
    interval_days: float
    next_due: date
    reps: int
    lapses: int


def review(state: ReviewState | None, outcome: str, today: date) -> ReviewState:
    quality = QUALITY[outcome]
    ease = state.ease if state else INITIAL_EASE
    reps = state.reps if state else 0
    lapses = state.lapses if state else 0

    ease = max(MIN_EASE, ease + 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))

    if quality < 3:
        reps = 0
        lapses += 1
        interval = LAPSE_INTERVAL
    else:
        reps += 1
        if reps == 1:
            interval = FIRST_INTERVAL
        elif reps == 2:
            interval = SECOND_INTERVAL
        else:
            interval = min(state.interval_days * ease, MAX_INTERVAL)

    return ReviewState(
        ease=ease,
        interval_days=interval,
        next_due=today + timedelta(days=round(interval)),
        reps=reps,
        lapses=lapses,
    )


def due_reviews(
    conn: sqlite3.Connection, today: date, lookahead_days: int = 0
) -> list[sqlite3.Row]:
    """Problems whose review is owed by today+lookahead_days, soonest first.

    The read half of this module: review() decides when a problem comes back,
    this reads back which ones have. The old `coach due` and the weekly analysis
    asked the same question with two copies of the query, which differed only in
    the horizon - so the horizon is the parameter and the query is shared.

    lookahead_days=0 means "owed today or overdue"; the weekly analysis passes
    its own default to cover the days ahead. See PLAN_LOOKAHEAD_DAYS for why a
    daily list must not widen it.
    """
    return conn.execute(
        """
        SELECT p.number, p.slug, p.title, p.difficulty, r.next_due
        FROM review_state r JOIN problems p ON p.number = r.problem_number
        WHERE r.next_due <= ?
        ORDER BY r.next_due
        """,
        ((today + timedelta(days=lookahead_days)).isoformat(),),
    ).fetchall()
