from itertools import combinations

from evals.bank.controls import PRELUDE, external_code

NUMBER = 1984
SLUG = "minimum-difference-between-highest-and-lowest-of-k-scores"
TITLE = "Minimum Difference Between Highest and Lowest of K Scores"
DIFFICULTY = "Easy"
SPLIT = "test"
METHOD = "minimumDifference"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    (([9, 4, 1, 7], 2), 2, "general"),
    (([1, 10, 20, 21], 2), 1, "general"),
    (([3, 9, 1, 5, 7], 3), 4, "general"),
    (([8, 30, 2, 25, 27], 3), 5, "general"),
    (([90], 1), 0, "edge"),
    (([8, 2], 1), 0, "edge"),
]

SCALE = ([(i * 7919) % 100_001 for i in range(1000)], 500)
SPACE_SCALE = ([(i * 7919) % 100_001 for i in range(1000)], 500)


def reference(nums, k):
    return min(max(group) - min(group) for group in combinations(nums, k))


def valid(nums, k):
    # 1 <= k <= nums.length <= 1000, 0 <= nums[i] <= 10^5
    return 1 <= k <= len(nums) <= 1000 and all(0 <= x <= 10**5 for x in nums)


def generate(rng):
    nums = [rng.randint(0, 20) for _ in range(rng.randint(1, 8))]
    return (nums, rng.randint(1, len(nums)))


MUTANTS = [
    {
        "id": "windows-over-unsorted-scores",
        "mutation": "missing-precondition",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def minimumDifference(self, nums: List[int], k: int) -> int:
        l, r = 0, k - 1
        res = float("inf")

        while r < len(nums):
            res = min(res, nums[r] - nums[l])
            l, r = l + 1, r + 1
        return res
''',
    },
    {
        "id": "skips-the-last-window",
        "mutation": "off-by-one",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def minimumDifference(self, nums: List[int], k: int) -> int:
        nums.sort()
        ans = nums[k - 1] - nums[0]

        for i in range(k, len(nums) - 1):
            ans = min(ans, nums[i] - nums[i - k + 1])

        return ans
''',
    },
    {
        "id": "rescans-every-window",
        "mutation": "brute-force",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def minimumDifference(self, nums: List[int], k: int) -> int:
        nums.sort()
        res = float("inf")
        for i in range(len(nums) - k + 1):
            window = nums[i:i + k]
            res = min(res, max(window) - min(window))
        return res
''',
    },
]

CLEAN_VARIANTS = []
