"""Fetch clean-control candidates from two MIT-licensed LeetCode repos, then judge them.

    uv run python -m evals.bank.import_external fetch 1 3 20   # add or refresh these problems
    uv run python -m evals.bank.import_external judge          # accept or reject every candidate
    uv run python -m evals.bank.import_external judge 1 3      # or just these problems' candidates

Both repos are pinned to a commit, so fetching the same problem always stores the same
code. `judge` needs a problem's module (its tests and reference), so a new problem is
fetched first - its module takes its CANONICAL from what was fetched - and judged once the
module exists. Network to GitHub only; no model calls, so no cost.
"""

import argparse
import re
from dataclasses import dataclass
from urllib.parse import quote

import httpx

from evals.bank import controls
from evals.bank.problems import load_all


@dataclass(frozen=True)
class Source:
    repo: str
    sha: str
    path: str  # a pattern over the repo tree whose `number` group is the problem number


SOURCES = {
    "neetcode": Source(
        repo="neetcode-gh/leetcode",
        sha="9f104d45b1efc8c2e42b6dcc7b1216cdf8c4f80e",
        path=r"python/(?P<number>\d{4})-[^/]+\.py",
    ),
    "walkccc": Source(
        repo="walkccc/LeetCode",
        sha="9b85aa15e086d0b5dc1ead7184bca547942e6ff6",
        # Some problems hold more than one solution (53.py, 53-2.py, 53-3.py). The
        # unsuffixed file is taken, so which of them enters is not a choice made here.
        path=r"solutions/(?P<number>\d+)\. [^/]+/(?P=number)\.py",
    ),
}
NOTICES_PATH = controls.BANK_DIR / "THIRD_PARTY_NOTICES.md"


def raw(source: Source, path: str) -> str:
    url = f"https://raw.githubusercontent.com/{source.repo}/{source.sha}/{quote(path)}"
    response = httpx.get(url, timeout=60, follow_redirects=True)
    response.raise_for_status()
    return response.text


def tree(source: Source) -> dict[int, str]:
    response = httpx.get(f"https://api.github.com/repos/{source.repo}/git/trees/{source.sha}",
                         params={"recursive": "1"}, timeout=60)
    response.raise_for_status()
    body = response.json()
    if body["truncated"]:
        raise RuntimeError(f"{source.repo}: GitHub truncated the tree, so a solution could be missed")
    paths = {}
    for item in body["tree"]:
        match = re.fullmatch(source.path, item["path"])
        if match:
            paths[int(match["number"])] = item["path"]
    return paths


def write_notices() -> None:
    sections = [
        "# Third-party code\n",
        ("`external_solutions.json` holds LeetCode solutions copied unmodified from the"
         " repositories below, under their MIT licenses, reproduced here.\n"),
    ]
    for name, source in SOURCES.items():
        sections.append(f"## {name}: {source.repo} @ {source.sha}\n")
        sections.append("```\n" + raw(source, "LICENSE").strip() + "\n```\n")
    NOTICES_PATH.write_text("\n".join(sections))


def fetch(numbers: list[int]) -> None:
    store = controls.load_store(controls.EXTERNAL_PATH)
    kept = [entry for entry in store["solutions"] if entry["number"] not in numbers]
    for name, source in SOURCES.items():
        paths = tree(source)
        for number in numbers:
            if number not in paths:
                print(f"  {name}: no solution for problem {number}")
                continue
            kept.append({"source": name, "number": number, "path": paths[number],
                         "code": raw(source, paths[number]), "status": None, "reason": None})
            print(f"  {name}: {paths[number]}")
    order = list(SOURCES)
    kept.sort(key=lambda entry: (entry["number"], order.index(entry["source"])))
    store = {"sources": {name: {"repo": s.repo, "sha": s.sha, "license": "MIT"}
                         for name, s in SOURCES.items()},
             "solutions": kept}
    controls.write_store(controls.EXTERNAL_PATH, store)
    write_notices()


def judge(numbers: list[int]) -> int:
    store = controls.load_store(controls.EXTERNAL_PATH)
    by_number: dict[int, list[dict]] = {}
    for entry in store["solutions"]:
        by_number.setdefault(entry["number"], []).append(entry)
    accepted = rejected = 0
    for problem in load_all():
        if numbers and problem.NUMBER not in numbers:
            continue
        for entry, reason in controls.judge(problem, by_number.get(problem.NUMBER, [])):
            entry["status"], entry["reason"] = ("rejected", reason) if reason else ("accepted", None)
            accepted += reason is None
            rejected += reason is not None
            print(f"  {problem.SLUG}/{entry['source']}: {entry['status']}"
                  + (f" - {reason}" if reason else ""))
    controls.write_store(controls.EXTERNAL_PATH, store)
    print(f"\n{accepted} accepted, {rejected} rejected")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("fetch").add_argument("numbers", type=int, nargs="+")
    commands.add_parser("judge").add_argument("numbers", type=int, nargs="*")
    args = parser.parse_args()
    if args.command == "fetch":
        fetch(args.numbers)
        return 0
    return judge(args.numbers)


if __name__ == "__main__":
    raise SystemExit(main())
