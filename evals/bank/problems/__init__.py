"""Feedback-bank fixtures.

Each module holds a verified-correct CANONICAL solution, TESTS (marked
"general" or "edge"), a SCALE input for timing, and MUTANTS derived from a
fixed taxonomy of common mistakes. Categories come from `oracle.classify`,
not from the `intended` field - that field only records what the mutation was
aiming for, so disagreements can be reported.

Scope note: array/string/DP problems only. Tree, graph and linked-list
fixtures would need node-construction harnesses; their patterns are covered by
the enrichment eval instead.

TESTS must respect the problem's stated LeetCode constraints. Feeding an empty
array to a problem whose constraints say `1 <= nums.length` invents a defect
that does not exist, and a reviewer is right to ignore it. Where a test was
removed for this reason the mutant it caught usually becomes indistinguishable
from the canonical solution, and `oracle.classify` discards it automatically.

CLEAN_VARIANTS are further clean controls: other correct solutions, each one proven
clean by `oracle.verify_clean` (it passes every test and is not measurably slower
than the canonical). Execution does not measure space, so a variant must also use no
more space than the canonical - an O(n) slice where the canonical needs O(1) is a
genuine finding, and the reviewer would be scored as a false positive for being right.

A variant's `control` says how it is scored. "representative" is another way a strong
candidate writes the optimal solution, and counts toward the headline false-positive
rate with the canonical. "regression" was written to probe a false positive an earlier
run already showed (`probes` names it), and is scored apart: a prompt revised after
reading that run is expected to do well on it, so pooling it would flatter the rate.
"""

import importlib
import pkgutil

MUTATION_TAXONOMY = {
    "wrong-init": "initialize an accumulator to a constant instead of the first element",
    "off-by-one": "shift a loop or binary-search bound by one",
    "missing-guard": "drop an empty/underflow check",
    "wrong-operator": "swap a comparison operator",
    "weaker-structure": "use a structure that loses information (set for a multiset)",
    "greedy-substitution": "replace an exhaustive search with a greedy choice",
    "missing-precondition": "drop a required sort or preprocessing step",
    "brute-force": "replace the optimal approach with exhaustive enumeration",
    "naive-recursion": "remove memoization from a recursive formulation",
    "unsafe-arithmetic": "use division where a zero can appear",
}


def load_all() -> list:
    modules = []
    for info in pkgutil.iter_modules(__path__):
        modules.append(importlib.import_module(f"{__name__}.{info.name}"))
    return sorted(modules, key=lambda m: m.NUMBER)
