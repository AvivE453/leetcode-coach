from evals.bank.controls import PRELUDE, external_code

NUMBER = 300
SLUG = "longest-increasing-subsequence"
TITLE = "Longest Increasing Subsequence"
DIFFICULTY = "Medium"
SPLIT = "dev"
METHOD = "lengthOfLIS"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    (([10, 9, 2, 5, 3, 7, 101, 18],), 4, "general"),
    (([0, 1, 0, 3, 2, 3],), 4, "general"),
    (([7, 7, 7, 7],), 1, "general"),
    (([1, 2],), 2, "general"),
    (([2, 1],), 1, "general"),
    (([5],), 1, "edge"),
]

SCALE = (list(range(18)),)
SPACE_SCALE = (list(range(2500)),)


def reference(nums):
    best = 0
    for chosen in range(1, 1 << len(nums)):
        picked = [x for i, x in enumerate(nums) if chosen >> i & 1]
        if all(picked[i] < picked[i + 1] for i in range(len(picked) - 1)):
            best = max(best, len(picked))
    return best


def generate(rng):
    # constraints: 1 <= nums.length <= 2500, -10^4 <= nums[i] <= 10^4
    return ([rng.randint(-3, 3) for _ in range(rng.randint(1, 8))],)


MUTANTS = [
    {
        "id": "equal-values-extend",
        "mutation": "wrong-operator",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def lengthOfLIS(self, nums: List[int]) -> int:
        LIS = [1] * len(nums)

        for i in range(len(nums) - 1, -1, -1):
            for j in range(i + 1, len(nums)):
                if nums[i] <= nums[j]:
                    LIS[i] = max(LIS[i], 1 + LIS[j])
        return max(LIS)
''',
    },
    {
        "id": "longest-increasing-run",
        "mutation": "greedy-substitution",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def lengthOfLIS(self, nums: List[int]) -> int:
        best = cur = 1
        for i in range(1, len(nums)):
            cur = cur + 1 if nums[i] > nums[i - 1] else 1
            best = max(best, cur)
        return best
''',
    },
    {
        "id": "every-subsequence",
        "mutation": "naive-recursion",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def lengthOfLIS(self, nums: List[int]) -> int:
        def longest(i, prev):
            if i == len(nums):
                return 0
            skip = longest(i + 1, prev)
            if prev is None or nums[i] > prev:
                return max(skip, 1 + longest(i + 1, nums[i]))
            return skip

        return longest(0, None)
''',
    },
]

CLEAN_VARIANTS = []
