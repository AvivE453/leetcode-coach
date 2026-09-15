"""Which code counts as a clean control, and the one door code from outside enters by.

External solutions are never edited: a solution that breaks a rule is rejected with its
reason, because fixing it would make it authored. And in the test split nothing authored
is scored at all - that is what makes a test number a held-out number.
"""

import json
import types

import pytest

from evals.bank import controls

CANONICAL = '''\
class Solution:
    def run(self, nums):
        return max(nums)
'''

LOOP = '''\
class Solution:
    def run(self, nums):
        best = nums[0]
        for x in nums:
            if x > best:
                best = x
        return best
'''

BROKEN = "class Solution:\n    def run(self, nums):\n        return nums[0]\n"


def make_problem(**overrides):
    problem = types.SimpleNamespace(
        NUMBER=7,
        SLUG="fake",
        SPLIT="dev",
        METHOD="run",
        CANONICAL=CANONICAL,
        CLEAN_VARIANTS=[],
        TESTS=[(([1, 5, 3],), 5, "general"), (([-4],), -4, "edge")],
        SCALE=(list(range(20000)),),
        SPACE_SCALE=(list(range(200_000)),),
        DIFFERENTIAL_CASES=200,
        reference=lambda nums: max(nums),
        generate=lambda rng: ([rng.randint(-50, 50) for _ in range(rng.randint(1, 8))],),
    )
    for key, value in overrides.items():
        setattr(problem, key, value)
    return problem


def candidate(code, source="neetcode"):
    return {"source": source, "number": 7, "code": code}


@pytest.fixture
def stores(tmp_path, monkeypatch):
    """Point both stores at empty files; returns a writer for the external one."""
    monkeypatch.setattr(controls, "EXTERNAL_PATH", tmp_path / "external.json")
    monkeypatch.setattr(controls, "PRIVATE_PATH", tmp_path / "private.json")

    def write(*entries):
        controls.EXTERNAL_PATH.write_text(json.dumps({"solutions": list(entries)}))
    return write


def test_a_method_defined_twice_is_rejected_not_fixed():
    """Only the second definition runs, so the code executed is not all the reviewer reads."""
    code = CANONICAL + "\n    def run(self, nums):\n        return sorted(nums)[-1]\n"

    [(_, reason)] = controls.judge(make_problem(), [candidate(code)])

    assert reason == "defines Solution.run 2 times"


def test_a_file_defining_solution_twice_is_rejected():
    [(_, reason)] = controls.judge(make_problem(), [candidate(CANONICAL + "\n\n" + LOOP)])

    assert reason == "defines class Solution 2 times"


def test_a_helper_method_beside_the_entry_point_is_fine():
    helper = '''\
class Solution:
    def run(self, nums):
        return self.largest(nums)

    def largest(self, nums):
        best = nums[0]
        for x in nums[1:]:
            best = x if x > best else best
        return best
'''
    [(_, reason)] = controls.judge(make_problem(SPACE_SCALE=(list(range(1000)),)), [candidate(helper)])

    assert reason is None


def test_a_reformatted_copy_of_the_canonical_is_a_duplicate():
    code = "class Solution:\n\n    def run(self, nums):\n        # the same, spaced out\n        return max( nums )\n"

    [(_, reason)] = controls.judge(make_problem(), [candidate(code)])

    assert reason == "same code as the canonical"


def test_code_the_oracle_cannot_prove_clean_is_rejected():
    [(_, reason)] = controls.judge(make_problem(), [candidate(BROKEN)])

    assert "not clean" in reason


def test_of_two_identical_new_solutions_only_the_first_is_kept():
    verdicts = controls.judge(make_problem(), [candidate(LOOP, "neetcode"), candidate(LOOP, "walkccc")])

    assert [reason for _, reason in verdicts] == [None, "same code as neetcode"]


def test_a_candidate_identical_to_a_control_from_another_source_is_a_duplicate():
    already = [{"id": "walkccc", "code": controls.PRELUDE + LOOP}]
    solve = {**candidate(LOOP, "aviv"), "solution_id": 3}

    [(_, reason)] = controls.judge(make_problem(), [solve], already)

    assert reason == "same code as walkccc"


def test_the_test_split_scores_no_authored_code(stores):
    stores({**candidate(LOOP, "walkccc"), "status": "accepted"},
           {**candidate(BROKEN), "status": "rejected"})
    variant = {"id": "loop", "control": "representative", "code": LOOP}

    held_out = controls.clean_controls(make_problem(SPLIT="test", CLEAN_VARIANTS=[variant]))
    tuning = controls.clean_controls(make_problem(SPLIT="dev", CLEAN_VARIANTS=[variant]))

    assert [c["id"] for c in held_out] == ["walkccc"]
    assert [c["id"] for c in tuning] == ["canonical", "loop", "walkccc"]


def test_a_canonical_taken_from_a_fetched_solution_carries_its_origin(stores):
    stores({**candidate(CANONICAL, "neetcode"), "status": "rejected"})
    problem = make_problem(SPLIT="test", CANONICAL=controls.PRELUDE + CANONICAL)

    [canonical] = controls.clean_controls(problem)

    assert (canonical["id"], canonical["origin"]) == ("canonical", "neetcode")
