"""Where a problem's clean controls come from, and the one door external code enters by.

A clean control is correct, optimal code the reviewer should report nothing on. Its
`origin` says who wrote it: "authored" for a CANONICAL or CLEAN_VARIANT written in this
repo, "neetcode" or "walkccc" for a solution copied from an MIT-licensed LeetCode repo
(import_external.py), and "aviv" for one of Aviv's own clean solves (import_private.py,
kept out of git).

Code from outside is never edited. `judge` rejects a solution that breaks a rule and
records why, because fixing it would make it authored - and authored code is exactly what
the test split is meant to be free of.
"""

import ast
import json
from pathlib import Path

from evals.bank import oracle

BANK_DIR = Path(__file__).resolve().parent
EXTERNAL_PATH = BANK_DIR / "external_solutions.json"
PRIVATE_PATH = BANK_DIR / "private" / "solves.json"

# What LeetCode's Python 3 environment has already imported when it runs a submission.
# Solutions written there use `List[int]`, `Counter` and `deque` without importing them
# and cannot run without it, so it is the one thing ever added to code from outside.
PRELUDE = (
    "from typing import *\n"
    "from collections import *\n"
    "from heapq import *\n"
    "from bisect import *\n"
    "from functools import *\n"
    "from itertools import *\n"
    "from math import inf\n"
    "import bisect, collections, functools, heapq, itertools, math, operator, re, string\n\n"
)


def load_store(path: Path) -> dict:
    if not path.exists():
        return {"solutions": []}
    return json.loads(path.read_text())


def write_store(path: Path, store: dict) -> None:
    """Written beside the store and renamed over it, so a reader never sees half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".partial")
    partial.write_text(json.dumps(store, indent=2, ensure_ascii=False) + "\n")
    partial.replace(path)


def candidate_id(entry: dict) -> str:
    return f"aviv-{entry['solution_id']}" if entry["source"] == "aviv" else entry["source"]


def external_code(source: str, number: int) -> str:
    """A fetched solution as it runs: PRELUDE, then the code exactly as published."""
    for entry in load_store(EXTERNAL_PATH)["solutions"]:
        if entry["source"] == source and entry["number"] == number:
            return PRELUDE + entry["code"]
    raise KeyError(f"no {source} solution for problem {number} - run import_external fetch first")


def solution_class(code: str) -> ast.ClassDef | None:
    for node in ast.parse(code).body:
        if isinstance(node, ast.ClassDef) and node.name == "Solution":
            return node
    return None


def shape(code: str) -> str:
    """The Solution class by structure: formatting, comments and PRELUDE never make a copy look new."""
    node = solution_class(code)
    return ast.dump(node if node is not None else ast.parse(code))


def definition_problem(code: str, method: str) -> str | None:
    """Why the code cannot be judged as written, or None.

    A second definition silently replaces the first when the code runs, so what executes
    would not be all a reviewer reads - and the reviewer could rightly remark on the rest.
    Helper methods beside the entry point are fine: LeetCode calls the method by name.
    """
    classes = [node for node in ast.parse(code).body
               if isinstance(node, ast.ClassDef) and node.name == "Solution"]
    if len(classes) != 1:
        return f"defines class Solution {len(classes)} times"
    definitions = sum(isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef) and item.name == method
                      for item in classes[0].body)
    if definitions != 1:
        return f"defines Solution.{method} {definitions} times"
    return None


def canonical_origin(problem) -> str:
    """"authored" unless the canonical is, structurally, a fetched solution."""
    canonical = shape(problem.CANONICAL)
    for entry in load_store(EXTERNAL_PATH)["solutions"]:
        try:
            fetched = shape(PRELUDE + entry["code"])
        except SyntaxError:
            continue
        if entry["number"] == problem.NUMBER and fetched == canonical:
            return entry["source"]
    return "authored"


def rejection(problem, candidate: dict, seen: dict[str, str]) -> str | None:
    code = PRELUDE + candidate["code"]
    try:
        unjudgeable = definition_problem(code, problem.METHOD)
    except SyntaxError as exc:
        return f"does not parse: {exc.msg}"
    if unjudgeable:
        return unjudgeable
    if shape(code) in seen:
        return f"same code as {seen[shape(code)]}"
    try:
        oracle.verify_clean(problem, {"id": candidate_id(candidate), "code": code})
    except Exception as exc:  # noqa: BLE001 - third-party code: any failure is a reason to reject
        return f"{type(exc).__name__}: {exc}"
    return None


def judge(problem, candidates: list[dict], already=()) -> list[tuple[dict, str | None]]:
    """Each candidate with the reason it is rejected, or None when it is a clean control.

    Candidates are judged in order, so of two structurally identical solutions the first
    one stays and the second is rejected as its duplicate - as is a candidate identical to
    a control `already` in the bank from another source.
    """
    seen = {shape(problem.CANONICAL): "the canonical"}
    for variant in problem.CLEAN_VARIANTS:
        seen[shape(variant["code"])] = variant["id"]
    for control in already:
        seen.setdefault(shape(control["code"]), control["id"])
    verdicts = []
    for candidate in candidates:
        reason = rejection(problem, candidate, seen)
        if reason is None:
            seen[shape(PRELUDE + candidate["code"])] = candidate_id(candidate)
        verdicts.append((candidate, reason))
    return verdicts


def clean_controls(problem) -> list[dict]:
    """Every clean control of a problem: id, code, control ("representative" or "regression"), origin.

    In the test split nothing authored counts. A test problem's canonical is a fetched
    solution; if none qualified, the authored one stays in the module as the timing
    reference for its mutants but is not scored as a control.
    """
    origin = canonical_origin(problem)
    authored_counts = problem.SPLIT != "test"
    controls = []
    if origin != "authored" or authored_counts:
        controls.append({"id": "canonical", "code": problem.CANONICAL,
                         "control": "representative", "origin": origin})
    if authored_counts:
        controls.extend({"id": variant["id"], "code": variant["code"],
                         "control": variant["control"], "origin": "authored"}
                        for variant in problem.CLEAN_VARIANTS)
    for path in (EXTERNAL_PATH, PRIVATE_PATH):
        controls.extend({"id": candidate_id(entry), "code": PRELUDE + entry["code"],
                         "control": "representative", "origin": entry["source"]}
                        for entry in load_store(path)["solutions"]
                        if entry["number"] == problem.NUMBER and entry["status"] == "accepted")
    return controls
