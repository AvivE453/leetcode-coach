"""Per-pattern mastery: one 1-5 score per pattern, folded over every solve.

Two signals go in. `outcome` is self-report - how the solve *felt*, on the same
1-5 scale SM-2 already uses for scheduling. A stored review is the external
judgement on the code itself. They disagree often enough to be worth blending:
a solve can feel clean and still carry a bug, or feel awful and come out optimal.
Reviews are on-demand, so most attempts have only the first signal; the review
weight then collapses into the outcome rather than assuming anything.

The fold is an exponential moving average, so recent solves move the score and
old ones fade without being thrown away - the same shape as SM-2's ease, one
level up: ease tracks one problem, this tracks one pattern.

Nothing here is stored. Every read replays the saved history (`load_history`),
because a review usually arrives *after* the solve was logged - sometimes days
later from the Solutions page - and computing on read is what lets it count the
moment it is saved, without any writer having to remember to refresh a score.
"""

import json
import sqlite3
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date

from coach.scheduler import QUALITY

OUTCOME_WEIGHT = 0.7
REVIEW_WEIGHT = 0.3
EMA_ALPHA = 0.2
WEAK_SCORE = 2.5
WEAK_MIN_ATTEMPTS = 5

VERDICT_MASTERY = {"optimal": 5, "acceptable": 4}


def is_weak(score: float, attempts: int) -> bool:
    """Whether one pattern's aggregates read as weak.

    Both halves of the rule live here because both are about what a mastery score
    means: how low it has to be, and how much practice it takes before the number
    is worth believing. They were split across two modules, so four files had to
    import from both to state one rule.

    This is a predicate on numbers, not the answer for a pattern - analyze() stays
    the only thing that produces `weak_patterns`, and callers still read weak as
    `pattern in analysis["weak_patterns"]` rather than calling this themselves.
    """
    return attempts >= WEAK_MIN_ATTEMPTS and score < WEAK_SCORE


def issue_ceiling(count: int) -> int:
    """How high a solve can score given how many findings it carries."""
    if count >= 5:
        return 1
    if count >= 3:
        return 2
    if count == 2:
        return 3
    return 5


def review_mastery(verdict: str, issues: Sequence[dict] = ()) -> int:
    """What the code actually did, 1-5, from a stored review.

    A bug is a misunderstanding of the pattern, so it scores lowest; an
    edge-case miss means the pattern is understood but the boundary was not.
    The ceiling applies on top, so more findings can only drag a verdict down:
    an "acceptable" carrying two issues is not the same solve as a spotless one.
    """
    if verdict == "needs-work":
        base = 1 if any(i["category"] == "bug" for i in issues) else 2
    else:
        base = VERDICT_MASTERY[verdict]
    return min(base, issue_ceiling(len(issues)))


def attempt_score(outcome: str, verdict: str | None = None, issues: Sequence[dict] = ()) -> float:
    """One solve, scored 1-5. Without a review the outcome carries full weight."""
    if verdict is None:
        return float(QUALITY[outcome])
    return OUTCOME_WEIGHT * QUALITY[outcome] + REVIEW_WEIGHT * review_mastery(verdict, issues)


def fold(scores: Iterable[float]) -> float | None:
    """EMA over one pattern's attempts, oldest first.

    Seeded with the first attempt rather than a neutral prior: unlike SM-2's
    ease, the first attempt here is a real observation, and blending it with an
    invented 3.0 would report a mastery nobody demonstrated.
    """
    score = None
    for s in scores:
        score = s if score is None else (1 - EMA_ALPHA) * score + EMA_ALPHA * s
    return score


@dataclass(frozen=True)
class ScoredAttempt:
    """One tagged solve, as mastery sees it."""

    pattern: str  # one of the solve's main patterns - never one of its secondaries
    problem: int
    day: date
    outcome: str
    score: float  # attempt_score(), with the review blended in when there is one


def load_history(conn: sqlite3.Connection) -> list[ScoredAttempt]:
    """Every tagged solve, scored, oldest first - the one read mastery is computed from.

    A solve with several main patterns is one attempt of each, at its full score:
    main patterns are equal, so the solve is neither split between them nor credited
    to the first alone. Ordered by date and then id, so two solves from the same day
    fold in logging order. Each review is joined onto the attempt it judges, so a
    review saved days later re-scores that attempt wherever it sits. Untagged solves
    are left out: with no pattern there is nothing to attribute them to.
    """
    rows = conn.execute(
        """
        SELECT tag.value AS pattern, a.problem_number, a.date, a.outcome,
               rv.verdict, rv.issues
        FROM attempts a
        JOIN solutions s ON s.attempt_id = a.id
        JOIN enrichments en ON en.solution_id = s.id
        JOIN json_each(en.main_patterns) tag
        LEFT JOIN reviews rv ON rv.solution_id = s.id
        ORDER BY a.date, a.id, tag.key
        """
    ).fetchall()

    history = []
    for r in rows:
        issues = json.loads(r["issues"]) if r["issues"] else []
        history.append(
            ScoredAttempt(
                pattern=r["pattern"],
                problem=r["problem_number"],
                day=date.fromisoformat(r["date"]),
                outcome=r["outcome"],
                score=attempt_score(r["outcome"], r["verdict"], issues),
            )
        )
    return history


def pattern_stats(history: Sequence[ScoredAttempt]) -> list[dict]:
    """Per-pattern practice aggregates, one row per pattern, ordered by name.

    The single answer to "how is each pattern going": how many problems it solved,
    how many attempts, how many were not clean (raw as `rough`, and as
    `struggle_rate`), the folded mastery score, and when it was last practiced -
    all taken from the same attempts, so the counts and the score can never
    describe different data. The home page's pattern table and the weekly analysis
    both read this.

    Pure over a loaded history, so where the patterns stood at an earlier date is
    this same function over the attempts before it, not a second query to drift.
    """
    by_pattern: dict[str, list[ScoredAttempt]] = {}
    for attempt in history:
        by_pattern.setdefault(attempt.pattern, []).append(attempt)

    stats = []
    for pattern in sorted(by_pattern):
        attempts = by_pattern[pattern]
        rough = sum(a.outcome != "clean" for a in attempts)
        stats.append(
            {
                "pattern": pattern,
                "solved": len({a.problem for a in attempts}),
                "attempts": len(attempts),
                "rough": rough,
                "struggle_rate": rough / len(attempts),
                "score": fold(a.score for a in attempts),
                "last_date": max(a.day for a in attempts),
            }
        )
    return stats
