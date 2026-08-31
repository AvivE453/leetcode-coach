import sqlite3
from typing import Literal

from pydantic import BaseModel

from coach import llm

PROMPT_VERSION = "review-v2"


class Issue(BaseModel):
    category: Literal["complexity", "bug", "edge-case"]
    description: str


class Review(BaseModel):
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


def review_solution(problem: sqlite3.Row, code: str) -> Review:
    prompt = PROMPT.format(
        number=problem["number"],
        title=problem["title"],
        difficulty=problem["difficulty"],
        code=code,
    )
    return llm.parse(prompt, Review)
