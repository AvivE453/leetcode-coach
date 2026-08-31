"""Run the oracle over every fixture and report what it can actually prove.

No API calls - pure execution. Run this after editing fixtures; anything
reported as DISCARD or MISMATCH needs attention before the bank is used.
"""

from evals.bank import oracle
from evals.bank.problems import load_all


def main() -> int:
    total = discarded = mismatched = 0
    counts: dict[str, int] = {}

    for problem in load_all():
        oracle.verify_canonical(problem)
        print(f"\n#{problem.NUMBER} {problem.TITLE}  (canonical OK)")
        for mutant in problem.MUTANTS:
            total += 1
            verdict = oracle.classify(problem, mutant["code"])
            if verdict.category is None:
                discarded += 1
                print(f"  DISCARD  {mutant['id']}: {verdict.evidence}")
                continue
            counts[verdict.category] = counts.get(verdict.category, 0) + 1
            flag = ""
            if verdict.category != mutant["intended"]:
                mismatched += 1
                flag = f"  [MISMATCH: aimed for {mutant['intended']}]"
            print(f"  {verdict.category:<11}{mutant['id']}: {verdict.evidence}{flag}")

    kept = total - discarded
    print(f"\n{'=' * 70}")
    print(f"{kept}/{total} mutants labelled by execution, {discarded} discarded"
          f" as indistinguishable, {mismatched} categorised differently than intended.")
    print("by category: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    print(f"clean controls: {len(load_all())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
