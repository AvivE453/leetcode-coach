"""Import Aviv's own clean solves as clean controls, kept out of git.

    uv run python -m evals.bank.import_private --db /path/to/snapshot.db

Reads a snapshot of the coach's database, never data/coach.db itself. Every solve whose
attempt was logged clean, for a problem the bank has, is judged exactly as an external
solution is (controls.judge) - so a solve that was clean to Aviv but is wrong, slow, or
heavy on memory is rejected with the reason. The verdicts go to evals/bank/private/solves.json,
which .gitignore keeps out of the public repository: RESULTS.md reports only numbers from it.
"""

import argparse
import sqlite3
from pathlib import Path

from coach import config
from evals.bank import controls
from evals.bank.problems import load_all


def clean_solves(db_path: Path, numbers: set[int]) -> list[dict]:
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            "SELECT s.id, s.problem_number, s.code FROM solutions s JOIN attempts a ON a.id = s.attempt_id"
            " WHERE a.outcome = 'clean' ORDER BY s.id"
        ).fetchall()
    finally:
        connection.close()
    return [{"source": "aviv", "solution_id": solution_id, "number": number, "code": code,
             "status": None, "reason": None}
            for solution_id, number, code in rows if number in numbers]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", type=Path, required=True, help="a snapshot of the coach's database")
    args = parser.parse_args()
    if args.db.resolve() == config.DB_PATH.resolve():
        parser.error("pass a snapshot of the database, not the live one")

    problems = {problem.NUMBER: problem for problem in load_all()}
    solves = clean_solves(args.db, set(problems))
    by_number: dict[int, list[dict]] = {}
    for solve in solves:
        by_number.setdefault(solve["number"], []).append(solve)

    accepted = 0
    for number, candidates in sorted(by_number.items()):
        problem = problems[number]
        already = [control for control in controls.clean_controls(problem) if control["origin"] != "aviv"]
        for solve, reason in controls.judge(problem, candidates, already):
            solve["status"], solve["reason"] = ("rejected", reason) if reason else ("accepted", None)
            accepted += reason is None
            print(f"  {problem.SLUG}/{controls.candidate_id(solve)}: {solve['status']}"
                  + (f" - {reason}" if reason else ""))
    controls.write_store(controls.PRIVATE_PATH, {"solutions": solves})
    print(f"\n{accepted} of {len(solves)} clean solves accepted as clean controls")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
