import json
import sqlite3
from typing import Literal, get_args

from pydantic import BaseModel

from coach import config, llm

PROMPT_VERSION = "enrich-v2"

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


def save_intended(conn: sqlite3.Connection, problem_number: int, pattern: str) -> None:
    conn.execute(
        "UPDATE problems SET intended_pattern = ? WHERE number = ?", (pattern, problem_number)
    )


def off_pattern_problems(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Solved problems whose canonical pattern was never used in any solution."""
    return conn.execute(
        """
        SELECT p.number, p.slug, p.title, p.difficulty, p.intended_pattern
        FROM problems p
        WHERE p.intended_pattern IS NOT NULL
          AND NOT EXISTS (
            SELECT 1
            FROM solutions s JOIN enrichments en ON en.solution_id = s.id
            WHERE s.problem_number = p.number
              AND (en.pattern = p.intended_pattern
                   OR en.secondary_patterns LIKE '%"' || p.intended_pattern || '"%')
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
