from evals.bank.controls import PRELUDE, external_code

NUMBER = 213
SLUG = "house-robber-ii"
TITLE = "House Robber II"
DIFFICULTY = "Medium"
SPLIT = "test"
METHOD = "rob"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    (([2, 3, 2],), 3, "general"),
    (([1, 2, 3, 1],), 4, "general"),
    (([1, 2, 3],), 3, "general"),
    (([2, 7, 9, 3, 1],), 11, "general"),
    (([5],), 5, "edge"),
    (([1, 5],), 5, "edge"),
]

SCALE = ([(i * 37) % 1001 for i in range(24)],)
SPACE_SCALE = ([(i * 37) % 1001 for i in range(100)],)


def reference(nums):
    n = len(nums)
    best = 0
    for chosen in range(1 << n):
        if chosen & (chosen >> 1):
            continue
        if n > 1 and chosen & 1 and chosen >> (n - 1) & 1:
            continue
        best = max(best, sum(x for i, x in enumerate(nums) if chosen >> i & 1))
    return best


def generate(rng):
    # constraints: 1 <= nums.length <= 100, 0 <= nums[i] <= 1000
    return ([rng.randint(0, 20) for _ in range(rng.randint(1, 10))],)


def is_edge(nums):
    return len(nums) == 1


MUTANTS = [
    {
        "id": "street-not-a-circle",
        "mutation": "missing-precondition",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def rob(self, nums: List[int]) -> int:
        return self.helper(nums)

    def helper(self, nums):
        rob1, rob2 = 0, 0

        for n in nums:
            newRob = max(rob1 + n, rob2)
            rob1 = rob2
            rob2 = newRob
        return rob2
''',
    },
    {
        "id": "a-lone-house-is-dropped",
        "mutation": "missing-guard",
        "intended": "edge-case",
        "code": PRELUDE + '''\
class Solution:
    def rob(self, nums: List[int]) -> int:
        return max(self.helper(nums[1:]), self.helper(nums[:-1]))

    def helper(self, nums):
        rob1, rob2 = 0, 0

        for n in nums:
            newRob = max(rob1 + n, rob2)
            rob1 = rob2
            rob2 = newRob
        return rob2
''',
    },
    {
        "id": "recursion-without-memo",
        "mutation": "naive-recursion",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def rob(self, nums: List[int]) -> int:
        return max(nums[0], self.helper(nums[1:]), self.helper(nums[:-1]))

    def helper(self, nums):
        if not nums:
            return 0
        return max(nums[0] + self.helper(nums[2:]), self.helper(nums[1:]))
''',
    },
]

CLEAN_VARIANTS = []
