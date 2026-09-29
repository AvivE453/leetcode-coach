from collections import Counter

from evals.bank.controls import PRELUDE, external_code

NUMBER = 442
SLUG = "find-all-duplicates-in-an-array"
TITLE = "Find All Duplicates in an Array"
DIFFICULTY = "Medium"
SPLIT = "test"
METHOD = "findDuplicates"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    (([4, 3, 2, 7, 8, 2, 3, 1],), [2, 3], "general"),
    (([1, 1, 2],), [1], "general"),
    (([5, 4, 6, 7, 9, 3, 10, 9, 5, 6],), [5, 6, 9], "general"),
    (([1, 2, 3, 4],), [], "general"),
    (([2, 2],), [2], "general"),
    (([1],), [], "edge"),
]

SCALE = (list(range(1, 2001)) + list(range(1, 1001)),)
SPACE_SCALE = (list(range(1, 2001)) + list(range(1, 1001)),)


def reference(nums):
    return [value for value, count in Counter(nums).items() if count == 2]


def normalize(duplicates):
    """LeetCode accepts the duplicates in any order."""
    return sorted(duplicates)


def valid(nums):
    # 1 <= n <= 10^5, 1 <= nums[i] <= n, each element appears once or twice
    return (1 <= len(nums) <= 10**5 and all(1 <= x <= len(nums) for x in nums)
            and max(Counter(nums).values()) <= 2)


def generate(rng):
    n = rng.randint(1, 10)
    once = rng.sample(range(1, n + 1), n - rng.randint(0, n // 2))
    nums = once + rng.sample(once, n - len(once))
    rng.shuffle(nums)
    return (nums,)


MUTANTS = [
    {
        "id": "indexes-by-the-flipped-sign",
        "mutation": "missing-precondition",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def findDuplicates(self, nums: List[int]) -> List[int]:
        res = []

        for n in nums:
            if nums[n - 1] < 0:
                res.append(n)
            nums[n - 1] = -nums[n - 1]

        return res
''',
    },
    {
        "id": "counts-each-value",
        "mutation": "brute-force",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def findDuplicates(self, nums: List[int]) -> List[int]:
        return [n for n in set(nums) if nums.count(n) == 2]
''',
    },
]

CLEAN_VARIANTS = []
