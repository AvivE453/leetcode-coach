import json
import sqlite3
from typing import Literal, get_args

from pydantic import BaseModel

from coach import config, llm

PROMPT_VERSION = "enrich-v3"

Pattern = Literal[
    "two-pointers",
    "sliding-window",
    "binary-search",
    "bfs",
    "dfs",
    "backtracking",
    "dp-1d",
    "dp-2d",
    "dp-knapsack",
    "dp-on-strings",
    "greedy",
    "heap",
    "monotonic-stack",
    "stack",
    "union-find",
    "trie",
    "intervals",
    "prefix-sum",
    "bit-manipulation",
    "math",
    "design",
    "topological-sort",
    "linked-list",
    "tree",
    "graph",
    "hashmap",
]

PATTERNS: tuple[str, ...] = get_args(Pattern)


class Enrichment(BaseModel):
    pattern: Pattern
    intended_pattern: Pattern
    intended_secondary_patterns: list[Pattern]
    secondary_patterns: list[Pattern]
    data_structures: list[str]
    key_trick: str
    time_complexity: str
    space_complexity: str


PROMPT = """\
You are tagging a LeetCode solution for a personal practice tracker. The tags feed
weakness analytics and similarity search, so they must describe HOW this specific
solution works - not the problem's official topic labels.

Problem: {number}. {title} (difficulty: {difficulty})
Official topic tags (coarse, for reference only): {tags}

Solution code:
```python
{code}
```

Fill in:
- pattern: the single algorithmic pattern that best describes this solution's approach,
  as written - even when that approach is suboptimal or wrong
- intended_pattern: the pattern the canonical optimal solution to this PROBLEM uses,
  regardless of how this code solved it (equal to pattern when the author took the
  intended approach)
- intended_secondary_patterns: other approaches that are genuinely canonical for this
  PROBLEM - judge the problem itself, not the code above. Include a pattern only if a
  strong candidate could lead with it and still be considered to have solved the
  problem properly. Never repeat intended_pattern; never list brute force, nor a
  generic supporting structure the real approach happens to use. Usually empty
- secondary_patterns: other patterns genuinely load-bearing in this solution (usually
  empty; never repeat the primary pattern)
- data_structures: concrete data structures the code relies on (e.g. "dict", "deque")
- key_trick: one sentence capturing the core insight, specific enough to distinguish
  this problem from others with the same pattern
- time_complexity / space_complexity: big-O of this code as written\
"""


def enrich_solution(problem: sqlite3.Row, code: str, model: str | None = None) -> Enrichment:
    prompt = PROMPT.format(
        number=problem["number"],
        title=problem["title"],
        difficulty=problem["difficulty"],
        tags=", ".join(json.loads(problem["official_tags"])) or "none",
        code=code,
    )
    return llm.parse(prompt, Enrichment, model=model)


def save(
    conn: sqlite3.Connection, solution_id: int, e: Enrichment, model: str | None = None
) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO enrichments
            (solution_id, pattern, secondary_patterns, data_structures,
             key_trick, time_complexity, space_complexity, model, prompt_version)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            solution_id,
            e.pattern,
            json.dumps(e.secondary_patterns),
            json.dumps(e.data_structures),
            e.key_trick,
            e.time_complexity,
            e.space_complexity,
            model or config.MODEL,
            PROMPT_VERSION,
        ),
    )


def save_intended(
    conn: sqlite3.Connection,
    problem_number: int,
    pattern: str,
    secondary: list[str] | None = None,
) -> None:
    """Store the problem's canonical approaches: the central one plus any alternates.

    `pattern` is dropped from `secondary` defensively - the two columns are read back
    as one set, and a duplicate there would show up as a repeated note.
    """
    extra = [p for p in dict.fromkeys(secondary or []) if p != pattern]
    conn.execute(
        "UPDATE problems SET intended_pattern = ?, intended_secondary_patterns = ? WHERE number = ?",
        (pattern, json.dumps(extra), problem_number),
    )


def canonical_patterns(intended: str | None, intended_secondary: list[str] | None) -> list[str]:
    """A problem's accepted approaches, central one first, deduplicated."""
    if not intended:
        return []
    return list(dict.fromkeys([intended, *(intended_secondary or [])]))


def off_pattern(
    pattern: str,
    secondary: list[str] | None,
    intended: str | None,
    intended_secondary: list[str] | None,
) -> bool:
    """True when a solve used none of the problem's canonical approaches.

    The sharp signal: it drives the `coach log` warning and the weekly plan's forced
    re-solve slot, so it must not fire for a solve that simply took a different but
    equally canonical route. Unknown canonical set (never enriched) is never off.
    """
    canonical = canonical_patterns(intended, intended_secondary)
    if not canonical:
        return False
    return {pattern, *(secondary or [])}.isdisjoint(canonical)


def unused_canonical(
    pattern: str,
    secondary: list[str] | None,
    intended: str | None,
    intended_secondary: list[str] | None,
) -> list[str]:
    """Canonical approaches this solve did not exercise, central one first.

    The soft signal behind "this problem can also be solved with ...". Purely
    informational: it is computed from stored columns, costs no API call, and is
    shown whether or not `off_pattern` fired.
    """
    used = {pattern, *(secondary or [])}
    return [p for p in canonical_patterns(intended, intended_secondary) if p not in used]


def off_pattern_problems(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Solved problems where no solution ever used any canonical approach.

    A problem clears this list as soon as one solve touches one accepted pattern -
    whether that is `intended_pattern` or one of `intended_secondary_patterns`, and
    whether it was that solve's primary or a secondary tag.
    """
    return conn.execute(
        """
        SELECT p.number, p.slug, p.title, p.difficulty, p.intended_pattern,
               p.intended_secondary_patterns
        FROM problems p
        WHERE p.intended_pattern IS NOT NULL
          AND NOT EXISTS (
            SELECT 1
            FROM solutions s JOIN enrichments en ON en.solution_id = s.id
            WHERE s.problem_number = p.number
              AND (en.pattern = p.intended_pattern
                   OR en.secondary_patterns LIKE '%"' || p.intended_pattern || '"%'
                   OR EXISTS (
                     SELECT 1 FROM json_each(p.intended_secondary_patterns) j
                     WHERE en.pattern = j.value
                        OR en.secondary_patterns LIKE '%"' || j.value || '"%'
                   ))
          )
        ORDER BY p.number
        """
    ).fetchall()


class QueryCard(BaseModel):
    pattern: Pattern
    key_trick: str


QUERY_PROMPT = """\
Given this LeetCode-style problem statement, predict how an optimal solution would work.

{statement}

- pattern: the algorithmic pattern an optimal solution would most likely use
- key_trick: one sentence describing the core insight of that solution\
"""


def hypothesize(statement: str, model: str | None = None) -> QueryCard:
    """Query-side enrichment for `coach similar --paste` (HyDE-style)."""
    return llm.parse(QUERY_PROMPT.format(statement=statement), QueryCard, model=model)


def missing(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Solutions that still need an enrichment row."""
    return conn.execute(
        """
        SELECT s.id AS solution_id, s.code, p.*
        FROM solutions s
        JOIN problems p ON p.number = s.problem_number
        LEFT JOIN enrichments e ON e.solution_id = s.id
        WHERE e.solution_id IS NULL
        ORDER BY s.id
        """
    ).fetchall()
