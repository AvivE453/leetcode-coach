import json
import sqlite3
from datetime import date
from typing import Literal

from pydantic import BaseModel

from coach import config, llm

PROMPT_VERSION = "review-v5"


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
{statement}
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
- issues: only genuine problems, judged against this problem's stated LeetCode
  constraints and guarantees - input sizes, value ranges, a non-empty input, a
  guaranteed answer, the allowed characters. Read them from the problem statement
  above when it is given; otherwise use what you know of this problem's actual
  constraints, never a generic worst case. An input the constraints exclude is not a
  flaw, and code that relies on a guarantee the problem gives is not a flaw. The three
  categories are mutually exclusive - decide which one applies by asking what kind of
  input breaks the code:
  - "bug": wrong on a REPRESENTATIVE input - an ordinary case a reader would write down
    first, with nothing degenerate about it. Name that input.
  - "edge-case": correct on representative inputs, wrong ONLY at a boundary or
    degenerate input that the constraints allow - empty, single element, all-negative,
    zeros, all-duplicates, already-sorted, integer limits. Name the boundary class.
  - "complexity": asymptotically worse than the standard optimal approach for this
    problem, but correct on every input. A faster algorithm that makes no practical
    difference at the input sizes the constraints allow does not count.
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


def review_solution(
    problem: sqlite3.Row, code: str, content: str | None, model: str | None = None
) -> Review:
    """One review of one solve. `content` is the problem statement, or None for none.

    None has no default on purpose. It is a real answer for a fifth of the catalog -
    the public API withholds the statement for paid-only problems - so both branches
    of the prompt run for good and both have to be measured. A default let the eval
    harness take the second branch without ever saying so, which meant `review-v5`
    named the prompt the coach sends *and* a different one the evals scored, with the
    cache file, the RESULTS.md heading and the reported version unable to tell them
    apart. A caller that has no statement now has to say so at the call site.
    """
    statement = f"\nProblem statement:\n{content}\n" if content else ""
    prompt = PROMPT.format(
        number=problem["number"],
        title=problem["title"],
        difficulty=problem["difficulty"],
        statement=statement,
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
