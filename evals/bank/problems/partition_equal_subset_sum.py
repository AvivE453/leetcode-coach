from itertools import product

from evals.bank.controls import PRELUDE, external_code

NUMBER = 416
SLUG = "partition-equal-subset-sum"
TITLE = "Partition Equal Subset Sum"
DIFFICULTY = "Medium"
SPLIT = "test"
METHOD = "canPartition"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    (([1, 5, 11, 5],), True, "general"),
    (([1, 2, 3, 5],), False, "general"),
    (([1, 1],), True, "general"),
    (([2, 2, 3, 5],), False, "general"),
    (([4, 4, 3, 3, 3, 3],), True, "general"),
    (([3, 3, 3, 4, 5],), True, "general"),
    (([7],), False, "edge"),
]

# All even with an odd half, so no subset reaches it and nothing returns early.
SCALE = ([2] * 199 + [4],)
SPACE_SCALE = ([(i % 100) + 1 for i in range(199)] + [51],)


def reference(nums):
    total = sum(nums)
    return any(2 * sum(num for num, taken in zip(nums, picks) if taken) == total
               for picks in product((False, True), repeat=len(nums)))


def valid(nums):
    # 1 <= nums.length <= 200, 1 <= nums[i] <= 100
    return 1 <= len(nums) <= 200 and all(1 <= x <= 100 for x in nums)


def generate(rng):
    return ([rng.randint(1, 12) for _ in range(rng.randint(1, 10))],)


MUTANTS = [
    {
        "id": "fills-the-half-largest-first",
        "mutation": "greedy-substitution",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def canPartition(self, nums: List[int]) -> bool:
        total = sum(nums)
        if total % 2:
            return False
        target = total // 2
        filled = 0
        for num in sorted(nums, reverse=True):
            if filled + num <= target:
                filled += num
        return filled == target
''',
    },
    {
        "id": "recursion-without-memo",
        "mutation": "naive-recursion",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def canPartition(self, nums: List[int]) -> bool:
        total = sum(nums)
        if total % 2:
            return False

        def dfs(i, target):
            if target == 0:
                return True
            if i == len(nums) or target < 0:
                return False
            return dfs(i + 1, target - nums[i]) or dfs(i + 1, target)

        return dfs(0, total // 2)
''',
    },
]

CLEAN_VARIANTS = []
