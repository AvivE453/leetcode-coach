"""What a review says about whether a solve was right, read one way for mastery and SM-2.

A solve carries two signals: the outcome it was logged with (how it felt) and, when one
was asked for, a review of the code. Mastery used to blend the review in while the
schedule ignored it, so a clean solve whose review reported a bug scored 3.8 for its
pattern and was still scheduled as a perfect recall. Both now grade an attempt through
effective_quality(), so they cannot disagree about what the attempt showed.

A review is a model's judgement, not an executed test, so it only ever caps a grade: a
reported bug holds an attempt down, but an "optimal" review never turns a solve that
needed hints into evidence of independent mastery.
"""

from collections.abc import Sequence
from datetime import date
from typing import TYPE_CHECKING, Literal

from coach.scheduler import QUALITY

if TYPE_CHECKING:
    from coach import history

Correctness = Literal["bug", "edge-case", "unspecified"]

# Worst first. A bug is wrong on an ordinary input; an edge case only at a boundary;
# "unspecified" is a needs-work verdict that names neither.
SEVERITY: tuple[Correctness, ...] = ("bug", "edge-case", "unspecified")

# Policy, not calibration: the highest 1-5 grade an attempt can earn when its review
# reports this. A bug grades like a failure, a boundary miss like needing hints, and an
# adverse verdict with no named failure like the milder of the two rather than nothing.
CORRECTNESS_CEILING: dict[Correctness, int] = {"bug": 1, "edge-case": 2, "unspecified": 2}


def correctness_finding(verdict: str | None, issues: Sequence[dict] = ()) -> Correctness | None:
    """The worst correctness problem a review reports, or None when it reports none.

    The categories outrank the verdict because they name the failing input: an
    "optimal" verdict carrying a bug is a bug. Complexity findings alone describe
    correct code, so they are no finding here - mastery weighs them on its own.
    """
    categories = {issue["category"] for issue in issues}
    if "bug" in categories:
        return "bug"
    if "edge-case" in categories:
        return "edge-case"
    if verdict == "needs-work":
        return "unspecified"
    return None


def effective_quality(outcome: str, verdict: str | None = None, issues: Sequence[dict] = ()) -> int:
    """An attempt's 1-5 grade: its logged outcome, capped by what its review found wrong."""
    finding = correctness_finding(verdict, issues)
    if finding is None:
        return QUALITY[outcome]
    return min(QUALITY[outcome], CORRECTNESS_CEILING[finding])


def findings(attempts: Sequence["history.Attempt"]) -> dict[int, Correctness]:
    """Each problem's worst finding on the last day it was practiced.

    The last day, not the last attempt, because the schedule grades a day by its worst
    attempt: a clean retry typed in minutes after a bug was found leaves the problem
    lapsed, so it must not clear the reason either. Practice on any later day moves past
    the finding - an unreviewed solve is trusted as logged.

    Pure over a loaded history, and over it in any order: the last day is taken from the
    attempts themselves rather than from where they sit in the list.
    """
    last_day: dict[int, date] = {}
    for attempt in attempts:
        number = attempt.problem.number
        last_day[number] = max(attempt.day, last_day.get(number, attempt.day))

    found: dict[int, list[Correctness]] = {}
    for attempt in attempts:
        number = attempt.problem.number
        if attempt.finding is not None and attempt.day == last_day[number]:
            found.setdefault(number, []).append(attempt.finding)
    return {number: min(worst, key=SEVERITY.index) for number, worst in found.items()}
