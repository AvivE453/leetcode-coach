import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta

QUALITY = {"clean": 5, "struggled": 3, "hints": 2, "failed": 1}
# The lowest grade that shows the problem was remembered. A day graded below it is a lapse,
# and the same day cannot complete approach practice (coach/corrections.py).
PASSING_QUALITY = 3
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


def review(state: ReviewState | None, quality: int, today: date) -> ReviewState:
    """One SM-2 step for a 1-5 grade: QUALITY for a bare outcome, capped by a review's
    findings in assessment.effective_quality(). Below PASSING_QUALITY is a lapse."""
    ease = state.ease if state else INITIAL_EASE
    reps = state.reps if state else 0
    lapses = state.lapses if state else 0

    ease = max(MIN_EASE, ease + 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))

    if quality < PASSING_QUALITY:
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


def replay(graded: list[tuple[date, int]]) -> ReviewState | None:
    """The review state one problem's (day, grade) attempts add up to.

    A day is one review, graded by its worst attempt. Solving a problem again in the
    same sitting - after reading the solution, or just once more - shows nothing about
    remembering it weeks later, yet counting every solve took three clean logs in one
    day to a 39-day interval. A failure is evidence whichever order it comes in, so it
    still grades its day, and three failed tries lapse the problem once instead of
    flooring its ease.

    The grades arrive already capped by any review, so this stays plain SM-2: a review
    saved days later changes the grade of the attempt it judges, and the replay puts
    that lapse on the day the attempt happened, never on the day the review arrived.
    """
    by_day: dict[date, list[int]] = {}
    for day, quality in graded:
        by_day.setdefault(day, []).append(quality)

    state = None
    for day in sorted(by_day):
        state = review(state, min(by_day[day]), day)
    return state


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
