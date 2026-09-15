import types

import pytest

from evals.bank import oracle

CANONICAL = '''\
class Solution:
    def run(self, nums):
        return max(nums)
'''

# Right on every hand-written test below, wrong on most longer inputs.
ONLY_SHORT_INPUTS = '''\
class Solution:
    def run(self, nums):
        return max(nums) if len(nums) < 5 else nums[0]
'''


def make_problem(**overrides):
    problem = types.SimpleNamespace(
        NUMBER=0,
        SLUG="fake",
        METHOD="run",
        CANONICAL=CANONICAL,
        TESTS=[
            (([1, 5, 3],), 5, "general"),
            (([2, 2],), 2, "general"),
            (([-4],), -4, "edge"),
        ],
        SCALE=(list(range(20000)),),
        SPACE_SCALE=(list(range(200_000)),),
        DIFFERENTIAL_CASES=200,
        reference=lambda nums: max(nums),
        generate=lambda rng: ([rng.randint(-50, 50) for _ in range(rng.randint(1, 8))],),
    )
    for key, value in overrides.items():
        setattr(problem, key, value)
    return problem


def test_a_solution_without_the_problems_method_is_refused():
    with pytest.raises(ValueError, match="a method run"):
        oracle.load_entry_point("class Solution:\n    def other(self, nums): pass\n", "run")


def test_a_solution_may_keep_helper_methods():
    """LeetCode calls the method by name, so a helper beside it is ordinary code."""
    helper = '''\
class Solution:
    def run(self, nums):
        return self.largest(nums)

    def largest(self, nums):
        return max(nums)
'''
    assert all(outcome.passed for outcome in oracle.run_tests(helper, make_problem().TESTS, "run"))


def test_each_input_gets_a_fresh_solution():
    """State left on self must not leak from one input into the next, as on LeetCode."""
    stateful = '''\
class Solution:
    def __init__(self):
        self.calls = 0

    def run(self, nums):
        self.calls += 1
        return max(nums) if self.calls == 1 else 0
'''
    assert all(outcome.passed for outcome in oracle.run_tests(stateful, make_problem().TESTS, "run"))


def test_verify_canonical_rejects_a_broken_canonical():
    broken = make_problem(CANONICAL="class Solution:\n    def run(self, nums):\n        return 0\n")
    with pytest.raises(AssertionError, match="fails its own tests"):
        oracle.verify_canonical(broken)


def test_verify_canonical_refuses_a_test_the_reference_disagrees_with():
    """A hand-written expectation is a claim too, and the reference checks it."""
    with pytest.raises(AssertionError, match="expects 4, but the reference returns 5"):
        oracle.verify_canonical(make_problem(TESTS=[(([1, 5, 3],), 4, "general")]))


def test_verify_canonical_refuses_a_canonical_only_the_reference_can_catch():
    with pytest.raises(AssertionError, match="disagrees with the reference"):
        oracle.verify_canonical(make_problem(CANONICAL=ONLY_SHORT_INPUTS))


def test_verify_clean_rejects_a_variant_the_oracle_cannot_prove_clean():
    variant = {"id": "first-only", "code": "class Solution:\n    def run(self, nums):\n        return nums[0]\n"}
    with pytest.raises(AssertionError, match=r"fake/first-only: clean variant is not clean \(bug"):
        oracle.verify_clean(make_problem(), variant)


def test_verify_clean_accepts_a_correct_variant():
    variant = {"id": "loop", "code": '''\
class Solution:
    def run(self, nums):
        best = nums[0]
        for x in nums:
            if x > best:
                best = x
        return best
'''}
    oracle.verify_clean(make_problem(), variant)


def test_verify_clean_rejects_a_variant_only_the_reference_can_catch():
    with pytest.raises(AssertionError, match="not clean \\(disagrees with the reference"):
        oracle.verify_clean(make_problem(), {"id": "short", "code": ONLY_SHORT_INPUTS})


def test_verify_clean_rejects_an_order_more_memory_than_the_canonical():
    """Timing cannot see an O(n) copy beside an O(1) canonical; the memory check can."""
    copying = {"id": "copy", "code": "class Solution:\n    def run(self, nums):\n        return max(list(nums))\n"}
    with pytest.raises(AssertionError, match="peaks at"):
        oracle.verify_clean(make_problem(), copying)


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


def test_a_mutant_only_the_reference_can_catch_is_too_weak_to_label():
    """Discarding it would call a wrong solution equivalent; labelling it would guess its kind."""
    with pytest.raises(oracle.TestsTooWeak, match="add a test for that input"):
        oracle.classify(make_problem(), ONLY_SHORT_INPUTS)


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
    monkeypatch.setattr(oracle, "time_at_scale", lambda code, method, scale: 0.0)

    with pytest.raises(AssertionError, match="too fast at scale to measure"):
        oracle.scale_baseline(make_problem())


def test_a_solution_too_fast_to_time_once_is_timed_over_repeated_calls():
    """A microsecond call is mostly clock noise; the ratio has to measure the code."""
    assert oracle.time_at_scale(CANONICAL, "run", ([1, 2, 3],)) > 0


def test_an_edge_label_is_refused_when_the_code_also_fails_ordinary_inputs():
    """Failing only the edge tests is not proof of an edge-case if a general input fails too."""
    drops_last = "class Solution:\n    def run(self, nums):\n        return max(nums[:-1]) if len(nums) > 1 else 0\n"
    problem = make_problem(is_edge=lambda nums: len(nums) == 1)

    with pytest.raises(oracle.TestsTooWeak, match="yet also an input is_edge does not call an edge"):
        oracle.classify(problem, drops_last)


def test_an_edge_label_stands_when_only_edge_inputs_fail():
    single_is_zero = "class Solution:\n    def run(self, nums):\n        return max(nums) if len(nums) > 1 else 0\n"
    problem = make_problem(is_edge=lambda nums: len(nums) == 1)

    assert oracle.classify(problem, single_is_zero).category == "edge-case"


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
