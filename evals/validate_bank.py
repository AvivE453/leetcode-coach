"""Run the oracle over every fixture and report what it can actually prove.

    uv run python -m evals.validate_bank              # every problem
    uv run python -m evals.validate_bank 125 191      # just these

No API calls - pure execution. Run this after editing fixtures or importing solutions:
anything reported as WEAK, DISCARD or MISMATCH needs attention before the bank is used,
and a clean control the oracle cannot prove clean stops the run.
"""

import sys

from evals.bank import controls, oracle
from evals.bank.problems import load_all


def main(numbers: set[int]) -> int:
    total = discarded = mismatched = weak = 0
    labels: dict[tuple[str, str], int] = {}
    clean: dict[tuple[str, str, str], int] = {}

    for problem in load_all():
        if numbers and problem.NUMBER not in numbers:
            continue
        oracle.verify_canonical(problem)
        print(f"\n#{problem.NUMBER} {problem.TITLE}  [{problem.SPLIT}]  (canonical OK)")
        for control in controls.clean_controls(problem):
            if control["id"] != "canonical":
                oracle.verify_clean(problem, control)
            key = (problem.SPLIT, control["control"], control["origin"])
            clean[key] = clean.get(key, 0) + 1
            print(f"  {'clean':<11}{control['id']} ({control['control']}, {control['origin']})")
        for mutant in problem.MUTANTS:
            total += 1
            try:
                verdict = oracle.classify(problem, mutant["code"])
            except oracle.TestsTooWeak as exc:
                weak += 1
                print(f"  {'WEAK':<11}{mutant['id']}: {exc}")
                continue
            if verdict.category is None:
                discarded += 1
                print(f"  {'DISCARD':<11}{mutant['id']}: {verdict.evidence}")
                continue
            key = (problem.SPLIT, verdict.category)
            labels[key] = labels.get(key, 0) + 1
            flag = ""
            if verdict.category != mutant["intended"]:
                mismatched += 1
                flag = f"  [MISMATCH: aimed for {mutant['intended']}]"
            print(f"  {verdict.category:<11}{mutant['id']}: {verdict.evidence}{flag}")

    print(f"\n{'=' * 70}")
    print(f"{total - discarded - weak}/{total} mutants labelled by execution, {discarded} discarded"
          f" as indistinguishable, {weak} with tests too weak to label them, {mismatched}"
          f" categorised differently than intended.")
    for split in sorted({split for split, _ in labels}):
        print(f"{split} flaws: " + ", ".join(f"{category} {n}" for (s, category), n in sorted(labels.items())
                                             if s == split))
    print("clean controls (split, control, origin):")
    for (split, control, origin), n in sorted(clean.items()):
        print(f"  {split:<5} {control:<15} {origin:<9} {n}")
    return 1 if weak else 0


if __name__ == "__main__":
    raise SystemExit(main({int(arg) for arg in sys.argv[1:]}))
