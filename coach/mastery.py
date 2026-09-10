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

`pattern_scores` is a derived cache, never a source of truth. It is rebuilt by
replaying history (`recompute_all`), because a review usually arrives *after* the
solve was logged - sometimes days later from the Solutions page - and an
incremental update at log time would never see it.
"""

import json
import sqlite3
from collections.abc import Iterable, Sequence
from datetime import date

from coach.scheduler import QUALITY

OUTCOME_WEIGHT = 0.7
REVIEW_WEIGHT = 0.3
EMA_ALPHA = 0.2
WEAK_SCORE = 2.5
WEAK_MIN_ATTEMPTS = 5

VERDICT_MASTERY = {"optimal": 5, "acceptable": 4}


def is_weak(score: float | None, attempts: int) -> bool:
    """Whether one pattern's aggregates read as weak.

    Both halves of the rule live here because both are about what a mastery score
    means: how low it has to be, and how much practice it takes before the number
    is worth believing. They were split across two modules, so four files had to
    import from both to state one rule.

    This is a predicate on numbers, not the answer for a pattern - analyze() stays
    the only thing that produces `weak_patterns`, and callers still read weak as
    `pattern in analysis["weak_patterns"]` rather than calling this themselves.
    """
    return score is not None and attempts >= WEAK_MIN_ATTEMPTS and score < WEAK_SCORE


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


def pattern_stats(conn: sqlite3.Connection) -> list[dict]:
    """Per-pattern practice aggregates, one row per pattern, ordered by name.

    The single answer to "how is each pattern going": how many attempts, how many
    were not clean (raw as `rough`, and as `struggle_rate`), the folded mastery
    score, and when it was last practiced. The home page's pattern table and the
    weekly analysis both read this - two callers once ran near-identical copies of
    this SQL that differed only in sort order and in which of rough/struggle_rate
    they kept, so each caller now takes what it needs from the shared rows.
    """
    rows = conn.execute(
        """
        SELECT en.pattern,
               COUNT(*) AS attempts,
               SUM(a.outcome != 'clean') AS rough,
               MAX(a.date) AS last_date,
               ps.score
        FROM attempts a
        JOIN solutions s ON s.attempt_id = a.id
        JOIN enrichments en ON en.solution_id = s.id
        LEFT JOIN pattern_scores ps ON ps.pattern = en.pattern
        GROUP BY en.pattern
        ORDER BY en.pattern
        """
    ).fetchall()
    return [
        {
            "pattern": r["pattern"],
            "attempts": r["attempts"],
            "rough": r["rough"],
            "struggle_rate": r["rough"] / r["attempts"],
            "score": r["score"],
            "last_date": date.fromisoformat(r["last_date"]),
        }
        for r in rows
    ]


def attempt_scores(
    conn: sqlite3.Connection, before: date | None = None
) -> dict[str, list[float]]:
    """Every scored attempt per pattern, oldest first - what `fold` reduces.

    `before` cuts the replay off at a date, which is how the weekly review asks
    where a pattern stood a week ago: the same history, one week short. A review
    written this week re-scores the attempt it belongs to on both sides of that
    cut, because the score is a function of the data, not of when it was read.
    """
    where = "WHERE a.date < ?" if before else ""
    rows = conn.execute(
        f"""
        SELECT en.pattern, a.outcome, rv.verdict, rv.issues
        FROM attempts a
        JOIN solutions s ON s.attempt_id = a.id
        JOIN enrichments en ON en.solution_id = s.id
        LEFT JOIN reviews rv ON rv.solution_id = s.id
        {where}
        ORDER BY a.date, a.id
        """,
        (before.isoformat(),) if before else (),
    ).fetchall()

    by_pattern: dict[str, list[float]] = {}
    for r in rows:
        issues = json.loads(r["issues"]) if r["issues"] else []
        by_pattern.setdefault(r["pattern"], []).append(
            attempt_score(r["outcome"], r["verdict"], issues)
        )
    return by_pattern


def recompute_all(conn: sqlite3.Connection) -> None:
    """Rebuild every pattern's score by replaying its attempts in order.

    Cheap enough to be the only recompute there is (hundreds of rows), which
    keeps the score a pure function of the data - no incremental bookkeeping to
    drift, and a late review re-scores the attempt it belongs to.
    """
    by_pattern = attempt_scores(conn)
    today = date.today().isoformat()
    conn.execute("DELETE FROM pattern_scores")
    conn.executemany(
        "INSERT INTO pattern_scores (pattern, score, attempts, updated_at) VALUES (?, ?, ?, ?)",
        [(p, fold(scores), len(scores), today) for p, scores in by_pattern.items()],
    )
    conn.commit()
