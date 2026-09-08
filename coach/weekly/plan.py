import json
import sqlite3
from dataclasses import dataclass
from typing import Literal

from coach import config, curriculum

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


# Which of build_plan's four rules put an item on the list. It doubles as the
# chip class the web UI styles, so it is set where the rule fires and travels
# with the item. It used to be recovered afterwards by matching the prefix of
# `reason` - which meant rewording a sentence meant for a human silently
# reclassified the item, with nothing to fail.
Kind = Literal["review", "re-solve", "weak-pattern", "curriculum"]


@dataclass(frozen=True)
class PlanItem:
    number: int
    slug: str
    title: str
    difficulty: str
    reason: str
    kind: Kind


def hard_cap(target: int) -> int:
    return max(1, target // 5)


def build_plan(conn: sqlite3.Connection, analysis: dict, target: int) -> list[PlanItem]:
    """Fill ~target slots: due reviews -> off-pattern re-solves -> weak-pattern
    picks from the unsolved curriculum -> curriculum progression. Hard problems
    are capped for new picks (mandatory reviews/re-solves are exempt)."""
    items: list[PlanItem] = []
    seen: set[int] = set()
    hards = 0

    def add(row, reason: str, kind: Kind, mandatory: bool = False) -> None:
        nonlocal hards
        if row["number"] in seen or len(items) >= target:
            return
        if not mandatory and row["difficulty"] == "Hard" and hards >= hard_cap(target):
            return
        if row["difficulty"] == "Hard":
            hards += 1
        seen.add(row["number"])
        items.append(
            PlanItem(row["number"], row["slug"], row["title"], row["difficulty"], reason, kind)
        )

    for row in analysis["due"]:
        add(row, f"review due {row['next_due']}", "review", mandatory=True)
    for row in analysis["off_pattern"]:
        add(
            row,
            f"re-solve with the intended pattern ({row['intended_pattern']})",
            "re-solve",
            mandatory=True,
        )

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
                add(row, f"weak pattern: {pattern}", "weak-pattern")
                picked += len(items) - before

    for row in unsolved:
        add(row, f"{config.CURRICULUM} progression", "curriculum")

    return items
