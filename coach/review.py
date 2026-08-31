import sqlite3
from typing import Literal

from pydantic import BaseModel

from coach import llm

PROMPT_VERSION = "review-v1"


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
- issues: only genuine problems, each categorized as
  - "complexity": the approach is asymptotically worse than the known optimal
  - "bug": the code produces a wrong answer on some valid input (say which input)
  - "edge-case": a valid input class the code mishandles (empty, single element,
    duplicates, overflow, ...)
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
