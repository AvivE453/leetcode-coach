"""Approach practice: what a problem still owes after it was solved with the wrong approach.

Three questions, kept apart. An attempt is off-pattern when its tags name none of the
problem's accepted approaches (enrich.off_pattern). Practice is outstanding while some
attempt was off-pattern and no attempt qualifies. It is due CORRECTION_INTERVAL_DAYS after
the latest attempt of any kind, so practising a problem - however it went - never brings it
straight back the next day.

An attempt qualifies when it used an accepted approach on a day that was not a failure day:
a day holding a grade below scheduler.PASSING_QUALITY, the line SM-2 lapses a day on. So a
solve that failed, needed hints, or whose review reported a bug never completes practice,
and neither does a clean retry typed in straight after one of those. The tags and the
success must be one attempt's: a failed DP solve beside a clean brute force is not "solved
with DP". Once an attempt qualifies the requirement stays met - trying another approach
later is an experiment, and forgetting is SM-2's business.

Nothing is read here and nothing is stored: the history comes from history.load(), and
every read replays it, so a review saved later, a tag backfilled by `coach enrich`, or a
canonical set widened by a new enrichment counts on the next page load. A problem reopened
that way is due three days after the practice itself - often already past - never three
days after the evidence was read.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from coach import enrich, history, scheduler

# Aviv's number. Deliberately not scheduler.LAPSE_INTERVAL, so the two can be tuned apart.
CORRECTION_INTERVAL_DAYS = 3

# Why a problem still owes approach practice, read off its latest tagged practice day.
Reason = Literal["wrong-approach", "failed", "assisted", "review-finding"]


@dataclass(frozen=True)
class Correction:
    """Approach practice a problem still owes."""

    problem: dict  # number, slug, title, difficulty
    accepted: list[str]  # the approaches that would complete it, central one first
    latest_attempt: date
    due: date
    reason: Reason
    evidence: tuple[int, ...]  # the attempts of the day `reason` describes


def problem_dict(problem: history.Problem) -> dict:
    """The problem as the web payload and the plan read it: a plain dict, not the record.

    `Correction.problem` is subscripted by web/app.py and weekly/plan.py, so the shape is
    part of the contract even though the history carries a richer record.
    """
    return {
        "number": problem.number,
        "slug": problem.slug,
        "title": problem.title,
        "difficulty": problem.difficulty,
    }


def evaluate(
    problem: dict, canonical: enrich.Canonical, attempts: Sequence[history.Attempt]
) -> Correction | None:
    """The approach practice one problem still owes, or None when it owes none.

    Pure over the problem's attempts, oldest first. Untagged attempts are neither evidence
    nor success; they only move the due date, because they were still practice.
    """
    tagged = [a for a in attempts if a.tagged]
    off = {a.id for a in tagged if enrich.off_pattern(a.main_patterns, a.secondary_patterns, *canonical)}
    if not off:
        return None
    failure_days = {a.day for a in attempts if a.grade < scheduler.PASSING_QUALITY}
    if any(a.id not in off and a.day not in failure_days for a in tagged):
        return None

    latest_tagged_day = [a for a in attempts if a.day == tagged[-1].day]
    latest = attempts[-1].day
    return Correction(
        problem=problem,
        accepted=enrich.canonical_patterns(*canonical),
        latest_attempt=latest,
        due=latest + timedelta(days=CORRECTION_INTERVAL_DAYS),
        reason=day_reason(latest_tagged_day, off),
        evidence=tuple(a.id for a in latest_tagged_day),
    )


def day_reason(day: Sequence[history.Attempt], off: set[int]) -> Reason:
    """Why one practice day left approach practice owed.

    A day whose tagged attempts all took the wrong approach is that. A day that did use an
    accepted approach must have been a failure day, explained by its outcomes before its
    reviews: a review only caps a grade the outcome had not already brought down.
    """
    if all(a.id in off for a in day if a.tagged):
        return "wrong-approach"
    outcomes = {a.outcome for a in day}
    if "failed" in outcomes:
        return "failed"
    if "hints" in outcomes:
        return "assisted"
    return "review-finding"


def owed(attempts: Sequence[history.Attempt]) -> list[Correction]:
    """Every problem in a history still owing approach practice, the soonest due first.

    Pure over the whole history: each problem is judged on its own attempts, and a problem
    with no canonical set is judged to owe nothing (enrich.off_pattern never fires on one).
    """
    found = []
    for group in history.by_problem(attempts).values():
        correction = evaluate(problem_dict(group[0].problem), group[0].problem.canonical, group)
        if correction:
            found.append(correction)
    return sorted(found, key=lambda c: (c.due, c.problem["number"]))
