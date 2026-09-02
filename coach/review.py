import json
import sqlite3
from datetime import date
from typing import Literal

from pydantic import BaseModel

from coach import config, llm

PROMPT_VERSION = "review-v3"


class Issue(BaseModel):
    category: Literal["complexity", "bug", "edge-case"]
    description: str


class Review(BaseModel):
    strengths: list[str]
    issues: list[Issue]
    time_complexity: str
    space_complexity: str
    optimal_time_complexity: str
    better_approach: str | None
    verdict: Literal["optimal", "acceptable", "needs-work"]


PROMPT = """\
You are reviewing a LeetCode solution for an interview-prep tracker. The author wants
honest, specific feedback they can act on before re-solving the problem.

Problem: {number}. {title} (difficulty: {difficulty})

Solution code:
```python
{code}
```

Report:
- strengths: specific things this code does well that are worth repeating - a good data
  structure choice, a clean invariant, a boundary handled correctly. Ground every one in
  something actually visible in the code; never generic praise like "clean and readable",
  and never restate what the problem asked for as though it were an achievement. Empty
  list when the solution is broken enough that nothing stands out.
- issues: only genuine problems. The three categories are mutually exclusive - decide
  which one applies by asking what kind of input breaks the code:
  - "bug": wrong on a REPRESENTATIVE input - an ordinary case a reader would write down
    first, with nothing degenerate about it. Name that input.
  - "edge-case": correct on representative inputs, wrong ONLY at a boundary or
    degenerate input - empty, single element, all-negative, zeros, all-duplicates,
    already-sorted, integer limits. Name the boundary class.
  - "complexity": asymptotically worse than the known optimal, but correct on every
    input.
  Precedence: if the failing input is a boundary case, it is "edge-case", never "bug",
  even though a boundary failure is also technically a wrong answer.
  A correct, optimal solution gets an EMPTY issues list - do not invent nitpicks.
- time_complexity / space_complexity: big-O of this code as written
- optimal_time_complexity: big-O of the best known approach for this problem
- better_approach: one short paragraph sketching the better approach, only when one
  exists; null when the solution is already optimal
- verdict: "optimal" (correct + best complexity), "acceptable" (correct but improvable),
  or "needs-work" (has a bug or mishandles edge cases)\
"""


def review_solution(problem: sqlite3.Row, code: str, model: str | None = None) -> Review:
    prompt = PROMPT.format(
        number=problem["number"],
        title=problem["title"],
        difficulty=problem["difficulty"],
        code=code,
    )
    return llm.parse(prompt, Review, model=model)


def save(
    conn: sqlite3.Connection, solution_id: int, r: Review, model: str | None = None
) -> None:
    """Store a review so it is paid for once, not re-bought on every look."""
    conn.execute(
        """
        INSERT OR REPLACE INTO reviews
            (solution_id, verdict, strengths, issues, time_complexity, space_complexity,
             optimal_time_complexity, better_approach, created_at, model, prompt_version)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            solution_id,
            r.verdict,
            json.dumps(r.strengths),
            json.dumps([i.model_dump() for i in r.issues]),
            r.time_complexity,
            r.space_complexity,
            r.optimal_time_complexity,
            r.better_approach,
            date.today().isoformat(),
            model or config.MODEL,
            PROMPT_VERSION,
        ),
    )


def load(conn: sqlite3.Connection, solution_id: int) -> Review | None:
    row = conn.execute(
        "SELECT * FROM reviews WHERE solution_id = ?", (solution_id,)
    ).fetchone()
    if row is None:
        return None
    return Review(
        strengths=json.loads(row["strengths"]),
        issues=[Issue(**i) for i in json.loads(row["issues"])],
        time_complexity=row["time_complexity"],
        space_complexity=row["space_complexity"],
        optimal_time_complexity=row["optimal_time_complexity"],
        better_approach=row["better_approach"],
        verdict=row["verdict"],
    )
