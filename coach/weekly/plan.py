import json
import sqlite3
from dataclasses import dataclass
from typing import Literal

from coach import assessment, config, corrections, curriculum

# Our fine-grained vocabulary -> official catalog tag, used to find NEW problems
# practicing a weak pattern (design decision #1: official tags pick problems,
# our tags diagnose weaknesses). Patterns without a usable official tag get no
# weak-pattern picks.
#
# Deliberately a subset of enrich.PATTERNS, not a copy of it: `intervals` is
# absent because LeetCode has no matching topic tag to search on (those problems
# are tagged array/sorting), so a weak `intervals` gets no targeted picks. A test
# keeps the keys a subset, so a typo here cannot silently stop targeting a
# pattern the way a missing entry deliberately does.
PATTERN_TO_TAG = {
    "two-pointers": "two-pointers",
    "sliding-window": "sliding-window",
    "binary-search": "binary-search",
    "bfs": "breadth-first-search",
    "dfs": "depth-first-search",
    "backtracking": "backtracking",
    "dp-1d": "dynamic-programming",
    "dp-2d": "dynamic-programming",
    "dp-knapsack": "dynamic-programming",
    "dp-on-strings": "dynamic-programming",
    "greedy": "greedy",
    "heap": "heap-priority-queue",
    "monotonic-stack": "monotonic-stack",
    "stack": "stack",
    "union-find": "union-find",
    "trie": "trie",
    "prefix-sum": "prefix-sum",
    "bit-manipulation": "bit-manipulation",
    "math": "math",
    "design": "design",
    "topological-sort": "topological-sort",
    "linked-list": "linked-list",
    "tree": "tree",
    "graph": "graph",
    "hashmap": "hash-table",
}

# So the weakest pattern cannot take every slot under Weak patterns from the others.
MAX_PER_WEAK_PATTERN = 3

# What a due review says when its last practice day holds a reported failure. It stays
# a "review": the finding only says why SM-2 brought the problem back, not another rule.
FINDING_REASON: dict[assessment.Correctness, str] = {
    "bug": "re-solve: review reported a bug",
    "edge-case": "re-solve: review reported an edge-case failure",
    "unspecified": "re-solve: review marked it needs-work",
}


# Which rule gave a reason: a due review, approach practice that is due ("re-solve"), a
# weak-pattern pick, or curriculum progression topping up Due. It doubles as the chip
# class the web UI styles, so it is set where the rule fires and travels with the reason.
# It used to be recovered afterwards by matching the prefix of the sentence - which meant
# rewording a sentence meant for a human silently reclassified the item, with nothing to fail.
Kind = Literal["review", "re-solve", "weak-pattern", "curriculum"]


@dataclass(frozen=True)
class Reason:
    kind: Kind
    text: str


@dataclass(frozen=True)
class PlanItem:
    """One problem on the plan, with every reason that applies to it today.

    Usually one. A problem owed both a review and approach practice is one item under
    Due carrying both - deduplicating used to keep the review's sentence and silently
    drop the approach to practise.
    """

    number: int
    slug: str
    title: str
    difficulty: str
    reasons: tuple[Reason, ...]


@dataclass(frozen=True)
class PlanSections:
    """Today's plan under its three headings, each holding at most `limit` problems.

    Each heading has its own budget: with one shared list of slots, a heavy review day
    pushed approach practice and weak-pattern picks off the page.
    """

    due: list[PlanItem]  # reviews due, most overdue first, then curriculum progression
    approach: list[PlanItem]  # approach practice that is due, with no review due alongside
    weak: list[PlanItem]  # unsolved problems picked for weak patterns
    reviews_owed: int  # every review due today, listed or not
    practice_owed: int  # due approach practice that is not already under a due review


def hard_cap(limit: int) -> int:
    return max(1, limit // 5)


def plan_item(problem, reasons: list[Reason]) -> PlanItem:
    return PlanItem(
        problem["number"], problem["slug"], problem["title"], problem["difficulty"], tuple(reasons)
    )


def review_reason(row: sqlite3.Row, findings: dict[int, assessment.Correctness]) -> Reason:
    finding = findings.get(row["number"])
    return Reason("review", FINDING_REASON[finding] if finding else f"review due {row['next_due']}")


def practice_reason(correction: corrections.Correction) -> Reason:
    return Reason("re-solve", f"practice an accepted approach: {' or '.join(correction.accepted)}")


def unsolved_curriculum(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Free curriculum problems never attempted, in the curriculum's own order."""
    order = {slug: i for i, slug in enumerate(curriculum.load(config.CURRICULUM))}
    rows = conn.execute(
        f"""
        SELECT p.number, p.slug, p.title, p.difficulty, p.official_tags
        FROM problems p
        WHERE p.{curriculum.FLAG_COLUMNS[config.CURRICULUM]} = 1
          AND p.paid_only = 0
          AND NOT EXISTS (SELECT 1 FROM attempts a WHERE a.problem_number = p.number)
        """
    ).fetchall()
    return sorted(rows, key=lambda r: order.get(r["slug"], len(order)))


def add_new_picks(
    heading: list[PlanItem],
    candidates: list[sqlite3.Row],
    limit: int,
    claimed: set[int],
    reason: Reason,
    most: int | None = None,
) -> None:
    """Add unclaimed candidates to one heading until it holds `limit`, or `most` were added.

    New problems are optional, so each heading caps its Hard ones at hard_cap(limit),
    counting a Hard review already under it. Owed work never meets the cap: build_plan
    adds it without this function.
    """
    added = 0
    for row in candidates:
        if len(heading) >= limit or (most is not None and added >= most):
            return
        hards = sum(item.difficulty == "Hard" for item in heading)
        if row["number"] in claimed or (row["difficulty"] == "Hard" and hards >= hard_cap(limit)):
            continue
        claimed.add(row["number"])
        heading.append(plan_item(row, [reason]))
        added += 1


def build_plan(conn: sqlite3.Connection, analysis: dict, limit: int) -> PlanSections:
    """Fill three headings of at most `limit` problems each, owed work first:

    1. Due: reviews due, worded by a reported failure when there is one. A problem that
       also owes approach practice stays here, as one item carrying both reasons.
    2. Approach practice that is due.
    3. Weak patterns: unsolved curriculum problems carrying a weak pattern's official
       tag, weakest pattern first and at most MAX_PER_WEAK_PATTERN each.
    4. Curriculum progression tops Due up to `limit`. It goes last, so it never takes a
       problem a weak pattern would have picked.

    Due claims every review due, listed or not. One that does not fit stays overdue and
    comes first tomorrow, instead of turning up under Approach practice without its review.
    """
    practice_due = {c.problem["number"]: c for c in analysis["corrections_due"]}
    due = []
    for row in analysis["due"][:limit]:
        reasons = [review_reason(row, analysis["findings"])]
        if row["number"] in practice_due:
            reasons.append(practice_reason(practice_due[row["number"]]))
        due.append(plan_item(row, reasons))
    claimed = {row["number"] for row in analysis["due"]}

    practice = [c for c in analysis["corrections_due"] if c.problem["number"] not in claimed]
    approach = [plan_item(c.problem, [practice_reason(c)]) for c in practice[:limit]]
    claimed.update(c.problem["number"] for c in practice)

    unsolved = unsolved_curriculum(conn)
    weak: list[PlanItem] = []
    for pattern in analysis["weak_patterns"]:
        tag = PATTERN_TO_TAG.get(pattern)
        if tag is None:
            continue
        tagged = [row for row in unsolved if tag in json.loads(row["official_tags"])]
        reason = Reason("weak-pattern", f"weak pattern: {pattern}")
        add_new_picks(weak, tagged, limit, claimed, reason, most=MAX_PER_WEAK_PATTERN)

    progression = Reason("curriculum", f"{config.CURRICULUM} progression")
    add_new_picks(due, unsolved, limit, claimed, progression)

    return PlanSections(
        due, approach, weak, reviews_owed=len(analysis["due"]), practice_owed=len(practice)
    )
