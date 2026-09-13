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

Nothing is stored. Every read replays the history, so a review saved later, a tag
backfilled by `coach enrich`, or a canonical set widened by a new enrichment counts on the
next page load. A problem reopened that way is due three days after the practice itself -
often already past - never three days after the evidence was read.
"""

import json
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from itertools import groupby
from typing import Literal, NamedTuple

from coach import assessment, enrich, scheduler

# Aviv's number. Deliberately not scheduler.LAPSE_INTERVAL, so the two can be tuned apart.
CORRECTION_INTERVAL_DAYS = 3

# Why a problem still owes approach practice, read off its latest tagged practice day.
Reason = Literal["wrong-approach", "failed", "assisted", "review-finding"]


@dataclass(frozen=True)
class Attempt:
    """One logged attempt, as approach practice reads it."""

    id: int
    day: date
    outcome: str
    grade: int  # assessment.effective_quality(): the outcome, capped by the attempt's review
    main_patterns: tuple[str, ...] | None  # None until tagged: unknown, and never evidence
    secondary_patterns: tuple[str, ...] = ()


class History(NamedTuple):
    """One attempted problem with a canonical set, and its attempts, oldest first."""

    problem: dict  # number, slug, title, difficulty
    canonical: enrich.Canonical
    attempts: list[Attempt]


@dataclass(frozen=True)
class Correction:
    """Approach practice a problem still owes."""

    problem: dict  # number, slug, title, difficulty
    accepted: list[str]  # the approaches that would complete it, central one first
    latest_attempt: date
    due: date
    reason: Reason
    evidence: tuple[int, ...]  # the attempts of the day `reason` describes


def load(conn: sqlite3.Connection, number: int | None = None) -> list[History]:
    """Every attempted problem that has a canonical set, with its attempts - the one read.

    Attempts drive the join: a solution never linked to an attempt is no dated practice,
    and a problem with a canonical set but no attempt is not loaded at all. Each attempt is
    graded with its review, as the SM-2 replay grades it. `number` narrows to one problem.
    """
    rows = conn.execute(
        """
        SELECT p.number, p.slug, p.title, p.difficulty,
               p.intended_pattern, p.intended_secondary_patterns,
               a.id AS attempt_id, a.date, a.outcome,
               en.main_patterns, en.secondary_patterns, rv.verdict, rv.issues
        FROM problems p
        JOIN attempts a ON a.problem_number = p.number
        LEFT JOIN solutions s ON s.attempt_id = a.id
        LEFT JOIN enrichments en ON en.solution_id = s.id
        LEFT JOIN reviews rv ON rv.solution_id = s.id
        WHERE p.intended_pattern IS NOT NULL AND (:number IS NULL OR p.number = :number)
        ORDER BY p.number, a.date, a.id
        """,
        {"number": number},
    ).fetchall()

    histories = []
    for _, group in groupby(rows, key=lambda row: row["number"]):
        problem_rows = list(group)
        first = problem_rows[0]
        histories.append(
            History(
                problem={key: first[key] for key in ("number", "slug", "title", "difficulty")},
                canonical=enrich.Canonical(
                    first["intended_pattern"], json.loads(first["intended_secondary_patterns"])
                ),
                attempts=[attempt_of(row) for row in problem_rows],
            )
        )
    return histories


def attempt_of(row: sqlite3.Row) -> Attempt:
    tagged = row["main_patterns"] is not None
    return Attempt(
        id=row["attempt_id"],
        day=date.fromisoformat(row["date"]),
        outcome=row["outcome"],
        grade=assessment.effective_quality(
            row["outcome"], row["verdict"], json.loads(row["issues"]) if row["issues"] else []
        ),
        main_patterns=tuple(json.loads(row["main_patterns"])) if tagged else None,
        secondary_patterns=tuple(json.loads(row["secondary_patterns"])) if tagged else (),
    )


def evaluate(
    problem: dict, canonical: enrich.Canonical, attempts: Sequence[Attempt]
) -> Correction | None:
    """The approach practice one problem still owes, or None when it owes none.

    Pure over the problem's attempts, oldest first. Untagged attempts are neither evidence
    nor success; they only move the due date, because they were still practice.
    """
    tagged = [a for a in attempts if a.main_patterns is not None]
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


def day_reason(day: Sequence[Attempt], off: set[int]) -> Reason:
    """Why one practice day left approach practice owed.

    A day whose tagged attempts all took the wrong approach is that. A day that did use an
    accepted approach must have been a failure day, explained by its outcomes before its
    reviews: a review only caps a grade the outcome had not already brought down.
    """
    if all(a.id in off for a in day if a.main_patterns is not None):
        return "wrong-approach"
    outcomes = {a.outcome for a in day}
    if "failed" in outcomes:
        return "failed"
    if "hints" in outcomes:
        return "assisted"
    return "review-finding"


def outstanding(conn: sqlite3.Connection) -> list[Correction]:
    """Every problem still owing approach practice, the soonest due first."""
    owed = [
        correction
        for history in load(conn)
        if (correction := evaluate(history.problem, history.canonical, history.attempts))
    ]
    return sorted(owed, key=lambda c: (c.due, c.problem["number"]))
