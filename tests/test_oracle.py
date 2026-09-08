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


def test_an_untimeable_canonical_is_refused_rather_than_guessed_at(monkeypatch):
    """No baseline means no ratio, and a missing ratio is not evidence of equivalence.

    Both unusable baselines used to be swallowed by one `if baseline and ...`: a
    canonical too slow to finish came back None and this mutant - which is far
    slower than the ratio requires - would have been reported as indistinguishable
    from it, or crashed formatting None as a duration.
    """
    # A tiny timeout rather than a genuinely slow canonical, so the test costs
    # milliseconds; what is under test is the missing measurement, not the clock.
    monkeypatch.setattr(oracle, "SCALE_TIMEOUT", 0.001)
    slow_canonical = '''\
class Solution:
    def run(self, nums):
        for _ in range(3_000_000):
            pass
        return max(nums)
'''
    problem = make_problem(CANONICAL=slow_canonical)

    with pytest.raises(AssertionError, match="exceeded .*s at scale"):
        oracle.scale_baseline(problem)
    with pytest.raises(AssertionError, match="exceeded .*s at scale"):
        oracle.classify(problem, CANONICAL)


def test_a_canonical_too_fast_to_measure_is_refused_too(monkeypatch):
    """The other unusable baseline: 0.0s divides into nothing.

    It took the same silent path, so a mutant taking the full timeout against an
    unmeasurable canonical was reported as equivalent to it.
    """
    monkeypatch.setattr(oracle, "time_at_scale", lambda code, scale: 0.0)

    with pytest.raises(AssertionError, match="too fast at scale to measure"):
        oracle.scale_baseline(make_problem())


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
