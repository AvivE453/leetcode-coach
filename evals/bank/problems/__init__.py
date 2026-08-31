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
