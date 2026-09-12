import json
import sqlite3
from typing import Literal, NamedTuple, get_args

from pydantic import BaseModel, Field, model_validator

from coach import config, llm

PROMPT_VERSION = "enrich-v5"

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
    main_patterns: list[Pattern] = Field(min_length=1)
    intended_pattern: Pattern
    intended_secondary_patterns: list[Pattern]
    secondary_patterns: list[Pattern]
    data_structures: list[str]
    key_trick: str
    time_complexity: str
    space_complexity: str

    @model_validator(mode="after")
    def list_each_pattern_once(self) -> "Enrichment":
        """Every main pattern is scored in full, so a repeat would count one solve twice."""
        self.main_patterns = list(dict.fromkeys(self.main_patterns))
        self.secondary_patterns = [
            p for p in dict.fromkeys(self.secondary_patterns) if p not in self.main_patterns
        ]
        return self


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
- main_patterns: every algorithmic pattern this solution is genuinely built on, as written
  - even when that approach is suboptimal or wrong. Judge this solution on its own merits;
  do not default to naming just one. List every pattern the solution cannot be properly
  described without (a memoized DFS computing a knapsack recurrence is genuinely both dfs
  and dp-knapsack, for example) - a step that merely supports the approach belongs in
  secondary_patterns instead. No main pattern ranks above another
- intended_pattern: the pattern the canonical optimal solution to this PROBLEM uses,
  regardless of how this code solved it (one of main_patterns when the author took the
  intended approach)
- intended_secondary_patterns: other approaches that are genuinely canonical for this
  PROBLEM - judge the problem itself, not the code above. Include a pattern only if a
  strong candidate could lead with it and still be considered to have solved the
  problem properly. Never repeat intended_pattern; never list brute force, nor a
  generic supporting structure the real approach happens to use. Usually empty
- secondary_patterns: other patterns genuinely load-bearing in this solution (usually
  empty; never repeat a main pattern)
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
            (solution_id, main_patterns, secondary_patterns, data_structures,
             key_trick, time_complexity, space_complexity, model, prompt_version)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            solution_id,
            json.dumps(e.main_patterns),
            json.dumps(e.secondary_patterns),
            json.dumps(e.data_structures),
            e.key_trick,
            e.time_complexity,
            e.space_complexity,
            model or config.MODEL,
            PROMPT_VERSION,
        ),
    )


class Canonical(NamedTuple):
    """A problem's canonical approaches as stored: the central one, then the alternates."""

    intended: str | None
    secondary: list[str]


def save_intended(
    conn: sqlite3.Connection,
    problem_number: int,
    pattern: str,
    secondary: list[str] | None = None,
) -> Canonical:
    """Store the problem's canonical approaches and return the set now stored.

    Judge a solve against that return value, never against the model's answer: after
    the merge below the two differ whenever the answer forgot an approach.

    The alternates ACCUMULATE across enrichments rather than replacing what is
    stored. Every re-solve re-enriches and calls this, and the model does not
    always name the same alternates twice - so replacing let a later enrichment
    narrow the canonical set and re-flag a solve that had legitimately used one
    of the dropped approaches, handing it a forced re-solve slot in the Daily Plan.
    Accumulating makes the set a record of every approach ever judged canonical,
    which is what off_pattern_problems() reads it as.

    `intended_pattern` still takes the newest answer, since it is the single
    central approach the off-pattern warning names; a previous central pattern
    is demoted into the alternates rather than dropped. `pattern` is dropped from
    the alternates - the two columns are read back as one set, and a duplicate
    would show up as a repeated note.
    """
    row = conn.execute(
        "SELECT intended_pattern, intended_secondary_patterns FROM problems WHERE number = ?",
        (problem_number,),
    ).fetchone()
    known: list[str] = []
    if row is not None:
        if row["intended_pattern"]:
            known.append(row["intended_pattern"])
        known.extend(json.loads(row["intended_secondary_patterns"] or "[]"))

    extra = [p for p in dict.fromkeys([*(secondary or []), *known]) if p != pattern]
    conn.execute(
        "UPDATE problems SET intended_pattern = ?, intended_secondary_patterns = ? WHERE number = ?",
        (pattern, json.dumps(extra), problem_number),
    )
    return Canonical(pattern, extra)


def canonical_patterns(intended: str | None, intended_secondary: list[str] | None) -> list[str]:
    """A problem's accepted approaches, central one first, deduplicated."""
    if not intended:
        return []
    return list(dict.fromkeys([intended, *(intended_secondary or [])]))


def off_pattern(
    main_patterns: list[str],
    secondary: list[str] | None,
    intended: str | None,
    intended_secondary: list[str] | None,
) -> bool:
    """True when a solve used none of the problem's canonical approaches.

    The sharp signal: it drives the off-pattern warning on a logged solve and the plan's forced
    re-solve slot, so it must not fire for a solve that simply took a different but
    equally canonical route - as any of its main patterns, or as a secondary.
    Unknown canonical set (never enriched) is never off.
    """
    canonical = canonical_patterns(intended, intended_secondary)
    if not canonical:
        return False
    return {*main_patterns, *(secondary or [])}.isdisjoint(canonical)


def unused_canonical(
    main_patterns: list[str],
    secondary: list[str] | None,
    intended: str | None,
    intended_secondary: list[str] | None,
) -> list[str]:
    """Canonical approaches this solve did not exercise, central one first.

    The soft signal behind "this problem can also be solved with ...". Purely
    informational: it is computed from stored columns, costs no API call, and is
    shown whether or not `off_pattern` fired.
    """
    used = {*main_patterns, *(secondary or [])}
    return [p for p in canonical_patterns(intended, intended_secondary) if p not in used]


def off_pattern_problems(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Solved problems where no solution ever used any canonical approach.

    A problem clears this list as soon as one solve used one accepted pattern -
    whether that is `intended_pattern` or one of `intended_secondary_patterns`, and
    whether the solve had it as a main pattern or a secondary. `used` flattens every
    solve's tags into (problem, pattern) pairs, so the check reads a single list.
    """
    return conn.execute(
        """
        WITH used AS (
            SELECT s.problem_number, tag.value AS pattern
            FROM solutions s
            JOIN enrichments en ON en.solution_id = s.id
            JOIN json_each(en.main_patterns) tag
            UNION
            SELECT s.problem_number, tag.value
            FROM solutions s
            JOIN enrichments en ON en.solution_id = s.id
            JOIN json_each(en.secondary_patterns) tag
        )
        SELECT p.number, p.slug, p.title, p.difficulty, p.intended_pattern,
               p.intended_secondary_patterns
        FROM problems p
        WHERE p.intended_pattern IS NOT NULL
          AND NOT EXISTS (
            SELECT 1 FROM used
            WHERE used.problem_number = p.number
              AND (used.pattern = p.intended_pattern
                   OR used.pattern IN (SELECT value FROM json_each(p.intended_secondary_patterns)))
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


def to_tag(conn: sqlite3.Connection, retag: bool = False) -> list[sqlite3.Row]:
    """Solutions to send to the model: the untagged ones, or every one when re-tagging.

    Re-tagging is how a changed prompt reaches solves tagged before it. It costs one
    API call per solution, so it is only ever asked for, never the default.
    """
    return conn.execute(
        """
        SELECT s.id AS solution_id, s.code, p.*
        FROM solutions s
        JOIN problems p ON p.number = s.problem_number
        LEFT JOIN enrichments e ON e.solution_id = s.id
        WHERE ? OR e.solution_id IS NULL
        ORDER BY s.id
        """,
        (retag,),
    ).fetchall()
