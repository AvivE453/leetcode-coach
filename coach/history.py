"""The one read of practice history: every attempt, with its tags and its review.

Four readers ask the same question of the database - mastery, approach practice, the
SM-2 replay and the plan's "why is this back" note - and each used to ask it with its
own join, its own JSON decoding and its own choice of inner or left join. The grade
formula already had one owner (`coach/assessment.py`), but the evidence it graded did
not, so a change to how a review attaches to an attempt meant editing four queries in
four modules, and missing one brought back exactly the disagreement assessment.py was
written to end - silently, with nothing to fail.

So the join lives here once and the readers are pure functions over what it returns.
An `Attempt` is the whole row: the attempt as logged, the solve's tags when it has
been tagged, and the review of that solve when one was bought. `grade` and `finding`
are derived rather than stored, so assessment.py stays the single owner of what a
review does to an attempt.

Ordered oldest first, across every problem, because that is the order mastery folds
in; `by_problem()` regroups without disturbing it. Nothing is cached: a review saved
days later, or a tag backfilled by `coach enrich`, counts on the next read.
"""

import json
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from coach import assessment, enrich


@dataclass(frozen=True)
class Problem:
    """The problem an attempt was made on, with the approaches accepted for it.

    Carried on the attempt rather than looked up beside it: approach practice judges
    tags against this set, and a second query for it is a second thing to keep in step.
    """

    number: int
    slug: str
    title: str
    difficulty: str
    canonical: enrich.Canonical


@dataclass(frozen=True)
class Attempt:
    """One logged attempt, with everything known about it at read time.

    `main_patterns` is None until the solve is tagged - unknown, which is never
    evidence, and is not the same as an empty list. `verdict` is None until a review
    is bought for it.
    """

    id: int
    problem: Problem
    day: date
    outcome: str
    minutes: int | None
    main_patterns: tuple[str, ...] | None
    secondary_patterns: tuple[str, ...]
    verdict: str | None
    issues: tuple[dict, ...]

    @property
    def tagged(self) -> bool:
        return self.main_patterns is not None

    @property
    def grade(self) -> int:
        """The 1-5 grade this attempt earned: its outcome, capped by what its review found."""
        return assessment.effective_quality(self.outcome, self.verdict, self.issues)

    @property
    def finding(self) -> assessment.Correctness | None:
        """The worst correctness problem its review reports, or None when it reports none."""
        return assessment.correctness_finding(self.verdict, self.issues)


QUERY = """
SELECT a.id, a.date, a.outcome, a.minutes,
       p.number, p.slug, p.title, p.difficulty,
       p.intended_pattern, p.intended_secondary_patterns,
       en.main_patterns, en.secondary_patterns,
       rv.verdict, rv.issues
FROM attempts a
JOIN problems p ON p.number = a.problem_number
LEFT JOIN solutions s ON s.attempt_id = a.id
LEFT JOIN enrichments en ON en.solution_id = s.id
LEFT JOIN reviews rv ON rv.solution_id = s.id
WHERE :number IS NULL OR p.number = :number
ORDER BY a.date, a.id
"""


def load(conn: sqlite3.Connection, number: int | None = None) -> list[Attempt]:
    """Every attempt ever logged, oldest first. `number` narrows to one problem.

    Attempts drive the join, and the solve, its tags and its review are all left-joined:
    an attempt logged before enrichment ran is still practice that happened, and dropping
    it would quietly change what the schedule replays. Two attempts on the same day keep
    the order they were logged in.
    """
    rows = conn.execute(QUERY, {"number": number}).fetchall()
    return [attempt_of(row) for row in rows]


def attempt_of(row: sqlite3.Row) -> Attempt:
    tagged = row["main_patterns"] is not None
    return Attempt(
        id=row["id"],
        problem=Problem(
            number=row["number"],
            slug=row["slug"],
            title=row["title"],
            difficulty=row["difficulty"],
            canonical=enrich.Canonical(
                row["intended_pattern"], json.loads(row["intended_secondary_patterns"])
            ),
        ),
        day=date.fromisoformat(row["date"]),
        outcome=row["outcome"],
        minutes=row["minutes"],
        main_patterns=tuple(json.loads(row["main_patterns"])) if tagged else None,
        secondary_patterns=tuple(json.loads(row["secondary_patterns"])) if tagged else (),
        verdict=row["verdict"],
        issues=tuple(json.loads(row["issues"])) if row["issues"] else (),
    )


def by_problem(attempts: Sequence[Attempt]) -> dict[int, list[Attempt]]:
    """The same attempts grouped by problem number, each group still oldest first.

    A dict rather than itertools.groupby, so the caller does not have to re-sort the
    history by problem first - which would cost mastery the chronological order it folds in.
    """
    grouped: dict[int, list[Attempt]] = {}
    for attempt in attempts:
        grouped.setdefault(attempt.problem.number, []).append(attempt)
    return grouped
