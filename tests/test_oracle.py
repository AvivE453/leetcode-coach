import types

import pytest

from evals.bank import oracle

CANONICAL = '''\
class Solution:
    def run(self, nums):
        return max(nums)
'''


def make_problem(**overrides):
    problem = types.SimpleNamespace(
        SLUG="fake",
        CANONICAL=CANONICAL,
        TESTS=[
            (([1, 5, 3],), 5, "general"),
            (([2, 2],), 2, "general"),
            (([-4],), -4, "edge"),
        ],
        SCALE=(list(range(20000)),),
    )
    for key, value in overrides.items():
        setattr(problem, key, value)
    return problem


def test_load_entry_point_requires_one_public_method():
    with pytest.raises(ValueError, match="exactly one public method"):
        oracle.load_entry_point("class Solution:\n    def a(self): pass\n    def b(self): pass\n")


def test_verify_canonical_rejects_a_broken_canonical():
    broken = make_problem(CANONICAL="class Solution:\n    def run(self, nums):\n        return 0\n")
    with pytest.raises(AssertionError, match="fails its own tests"):
        oracle.verify_canonical(broken)


def test_general_failure_is_a_bug():
    mutant = '''\
class Solution:
    def run(self, nums):
        return nums[0]
'''
    verdict = oracle.classify(make_problem(), mutant)
    assert verdict.category == "bug"
    assert "[1, 5, 3]" in verdict.evidence


def test_failure_only_on_edge_tests_is_an_edge_case():
    mutant = '''\
class Solution:
    def run(self, nums):
        return max(nums + [0])
'''
    verdict = oracle.classify(make_problem(), mutant)
    assert verdict.category == "edge-case"
    assert "-4" in verdict.evidence


def test_correct_but_slow_is_a_complexity_flaw():
    mutant = '''\
class Solution:
    def run(self, nums):
        best = nums[0]
        for x in nums:
            for y in nums[:200]:
                if x > best and y is not None:
                    best = x
        return best
'''
    verdict = oracle.classify(make_problem(), mutant)
    assert verdict.category == "complexity"
    assert "slower at scale" in verdict.evidence


def test_equivalent_mutant_is_discarded():
    mutant = '''\
class Solution:
    def run(self, nums):
        best = nums[0]
        for x in nums:
            if x > best:
                best = x
        return best
'''
    verdict = oracle.classify(make_problem(), mutant)
    assert verdict.category is None
    assert "indistinguishable" in verdict.evidence


def test_crash_counts_as_a_failure():
    mutant = '''\
class Solution:
    def run(self, nums):
        raise ValueError("boom")
'''
    verdict = oracle.classify(make_problem(), mutant)
    assert verdict.category == "bug"
    assert "ValueError" in verdict.evidence


def test_infinite_loop_times_out_rather_than_hanging():
    mutant = '''\
class Solution:
    def run(self, nums):
        while True:
            pass
'''
    verdict = oracle.classify(make_problem(), mutant)
    assert verdict.category == "bug"
    assert "timed out" in verdict.evidence
