from collections.abc import Sequence
from datetime import date, timedelta

from coach import history

WINDOW_DAYS = 7


def window(attempts: Sequence[history.Attempt], today: date) -> dict:
    """Everything that happened in the last 7 days, one row per attempt.

    Each attempt carries its main patterns as a list - empty when the solve was
    never tagged, which is still a solve, just one with nothing to attribute it to.

    The rows are the weekly table's own shape, not an Attempt: /api/weekly hands them
    to the browser as they are, so the keys here are what `weekly.js` reads and `date`
    stays the ISO string JSON would have made of it anyway.
    """
    start = today - timedelta(days=WINDOW_DAYS - 1)
    rows = [
        {
            "date": attempt.day.isoformat(),
            "problem_number": attempt.problem.number,
            "title": attempt.problem.title,
            "difficulty": attempt.problem.difficulty,
            "outcome": attempt.outcome,
            "minutes": attempt.minutes,
            "main_patterns": list(attempt.main_patterns or ()),
        }
        for attempt in attempts
        if attempt.day >= start
    ]
    return {
        "start": start,
        "end": today,
        "attempts": rows,
        "distinct_problems": len({r["problem_number"] for r in rows}),
    }
