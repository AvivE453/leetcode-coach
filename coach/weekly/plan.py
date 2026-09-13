import json
import sqlite3
from dataclasses import dataclass
from typing import Literal

from coach import assessment, config, corrections, curriculum

# Our fine-grained vocabulary -> official catalog tag, used to find NEW problems
# practicing a weak pattern (design decision #1: official tags pick problems,
# our tags diagnose weaknesses). Patterns without a usable official tag fall
# through to plain curriculum progression.
#
# Deliberately a subset of enrich.PATTERNS, not a copy of it: `intervals` is
# absent because LeetCode has no matching topic tag to search on (those problems
# are tagged array/sorting), so a weak `intervals` gets no targeted picks and
# falls through. A test keeps the keys a subset, so a typo here cannot silently
# stop targeting a pattern the way a missing entry deliberately does.
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

MAX_PER_WEAK_PATTERN = 3

# What a due review says when its last practice day holds a reported failure. It stays
# a "review": the finding only says why SM-2 brought the problem back, not another rule.
FINDING_REASON: dict[assessment.Correctness, str] = {
    "bug": "re-solve: review reported a bug",
    "edge-case": "re-solve: review reported an edge-case failure",
    "unspecified": "re-solve: review marked it needs-work",
}


# Which of build_plan's four rules gave a reason: a due review, approach practice that is
# due ("re-solve"), a weak-pattern pick, or curriculum progression. It doubles as the chip
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
    """One problem on the list, with every reason that applies to it today.

    Usually one. A problem owed both a review and approach practice is one item in one
    slot carrying both - deduplicating used to keep the review's sentence and silently
    drop the approach to practise.
    """

    number: int
    slug: str
    title: str
    difficulty: str
    reasons: tuple[Reason, ...]


def hard_cap(target: int) -> int:
    return max(1, target // 5)


def review_reason(row: sqlite3.Row, findings: dict[int, assessment.Correctness]) -> Reason:
    finding = findings.get(row["number"])
    return Reason("review", FINDING_REASON[finding] if finding else f"review due {row['next_due']}")


def practice_reason(correction: corrections.Correction) -> Reason:
    return Reason("re-solve", f"practice an accepted approach: {' or '.join(correction.accepted)}")


def build_plan(conn: sqlite3.Connection, analysis: dict, target: int) -> list[PlanItem]:
    """Fill ~target slots: due reviews (worded by a reported failure when there is
    one) -> approach practice that is due -> weak-pattern picks from the unsolved
    curriculum -> curriculum progression. Hard problems are capped for new picks
    (mandatory reviews and approach practice are exempt)."""
    items: list[PlanItem] = []
    seen: set[int] = set()
    hards = 0

    def add(problem, reasons: list[Reason], mandatory: bool = False) -> None:
        nonlocal hards
        if problem["number"] in seen or len(items) >= target:
            return
        if not mandatory and problem["difficulty"] == "Hard" and hards >= hard_cap(target):
            return
        if problem["difficulty"] == "Hard":
            hards += 1
        seen.add(problem["number"])
        items.append(
            PlanItem(
                problem["number"],
                problem["slug"],
                problem["title"],
                problem["difficulty"],
                tuple(reasons),
            )
        )

    practice_due = {c.problem["number"]: c for c in analysis["corrections_due"]}
    for row in analysis["due"]:
        reasons = [review_reason(row, analysis["findings"])]
        if row["number"] in practice_due:
            reasons.append(practice_reason(practice_due[row["number"]]))
        add(row, reasons, mandatory=True)
    for correction in analysis["corrections_due"]:
        add(correction.problem, [practice_reason(correction)], mandatory=True)

    order = {slug: i for i, slug in enumerate(curriculum.load(config.CURRICULUM))}
    unsolved = conn.execute(
        f"""
        SELECT p.number, p.slug, p.title, p.difficulty, p.official_tags
        FROM problems p
        WHERE p.{curriculum.FLAG_COLUMNS[config.CURRICULUM]} = 1
          AND p.paid_only = 0
          AND NOT EXISTS (SELECT 1 FROM attempts a WHERE a.problem_number = p.number)
        """
    ).fetchall()
    unsolved = sorted(unsolved, key=lambda r: order.get(r["slug"], len(order)))

    for pattern in analysis["weak_patterns"]:
        tag = PATTERN_TO_TAG.get(pattern)
        if tag is None:
            continue
        picked = 0
        for row in unsolved:
            if picked >= MAX_PER_WEAK_PATTERN or len(items) >= target:
                break
            if row["number"] not in seen and tag in json.loads(row["official_tags"]):
                before = len(items)
                add(row, [Reason("weak-pattern", f"weak pattern: {pattern}")])
                picked += len(items) - before

    for row in unsolved:
        add(row, [Reason("curriculum", f"{config.CURRICULUM} progression")])

    return items
