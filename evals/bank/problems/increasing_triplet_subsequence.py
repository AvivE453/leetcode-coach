from itertools import combinations

from evals.bank.controls import PRELUDE, external_code

NUMBER = 334
SLUG = "increasing-triplet-subsequence"
TITLE = "Increasing Triplet Subsequence"
DIFFICULTY = "Medium"
SPLIT = "test"
METHOD = "increasingTriplet"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    (([1, 2, 3, 4, 5],), True, "general"),
    (([5, 4, 3, 2, 1],), False, "general"),
    (([2, 1, 5, 0, 4, 6],), True, "general"),
    (([1, 1, 2],), False, "general"),
    (([2, 1, 5, 0, 3],), False, "general"),
    (([20, 100, 10, 12, 5, 13],), True, "general"),
    (([-3, -2, -5, -1],), True, "general"),
    (([1],), False, "edge"),
    (([1, 2],), False, "edge"),
    (([-2**31, 0, 2**31 - 1],), True, "edge"),
]

SCALE = (list(range(3000, 0, -1)),)
SPACE_SCALE = (list(range(3000, 0, -1)),)


def reference(nums):
    return any(a < b < c for a, b, c in combinations(nums, 3))


def valid(nums):
    # 1 <= nums.length <= 5 * 10^5, -2^31 <= nums[i] <= 2^31 - 1
    return 1 <= len(nums) <= 5 * 10**5 and all(-2**31 <= x <= 2**31 - 1 for x in nums)


def generate(rng):
    return ([rng.randint(-5, 5) for _ in range(rng.randint(1, 9))],)


MUTANTS = [
    {
        "id": "equal-counts-as-smaller",
        "mutation": "wrong-operator",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def increasingTriplet(self, nums: List[int]) -> bool:
        first = float('inf')
        second = float('inf')

        for num in nums:
            if num < first:
                first = num
            elif num <= second:
                second = num
            else:
                return True

        return False
''',
    },
    {
        "id": "zero-as-the-sentinel",
        "mutation": "wrong-init",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def increasingTriplet(self, nums: List[int]) -> bool:
        first = second = 0

        for num in nums:
            if num <= first:
                first = num
            elif num <= second:
                second = num
            else:
                return True

        return False
''',
    },
    {
        "id": "scans-both-sides-of-each-middle",
        "mutation": "brute-force",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def increasingTriplet(self, nums: List[int]) -> bool:
        for j in range(1, len(nums) - 1):
            if min(nums[:j]) < nums[j] < max(nums[j + 1:]):
                return True
        return False
''',
    },
]

CLEAN_VARIANTS = []
