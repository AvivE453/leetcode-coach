from evals.bank.controls import PRELUDE, external_code

NUMBER = 152
SLUG = "maximum-product-subarray"
TITLE = "Maximum Product Subarray"
DIFFICULTY = "Medium"
SPLIT = "test"
METHOD = "maxProduct"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    (([2, 3, -2, 4],), 6, "general"),
    (([-2, 0, -1],), 0, "general"),
    (([-2, 3, -4],), 24, "general"),
    (([-1, -1],), 1, "general"),
    (([-2],), -2, "edge"),
    (([0],), 0, "edge"),
]

SCALE = ([1, -1, 1, 1] * 750,)
SPACE_SCALE = ([1, -1] * 10_000,)


def reference(nums):
    best = nums[0]
    for i in range(len(nums)):
        product = 1
        for j in range(i, len(nums)):
            product *= nums[j]
            best = max(best, product)
    return best


def generate(rng):
    # constraints: 1 <= nums.length <= 2 * 10^4, -10 <= nums[i] <= 10
    return ([rng.randint(-3, 3) for _ in range(rng.randint(1, 8))],)


def is_edge(nums):
    return len(nums) == 1


MUTANTS = [
    {
        "id": "tracks-only-the-maximum",
        "mutation": "weaker-structure",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def maxProduct(self, nums: List[int]) -> int:
        res = nums[0]
        curMax = 1

        for n in nums:
            curMax = max(n * curMax, n)
            res = max(res, curMax)
        return res
''',
    },
    {
        "id": "best-starts-at-zero",
        "mutation": "wrong-init",
        "intended": "edge-case",
        "code": PRELUDE + '''\
class Solution:
    def maxProduct(self, nums: List[int]) -> int:
        # O(n)/O(1) : Time/Memory
        res = 0
        curMin, curMax = 1, 1

        for n in nums:

            tmp = curMax * n
            curMax = max(n * curMax, n * curMin, n)
            curMin = min(tmp, n * curMin, n)
            res = max(res, curMax)
        return res
''',
    },
    {
        "id": "every-subarray",
        "mutation": "brute-force",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def maxProduct(self, nums: List[int]) -> int:
        res = nums[0]
        for i in range(len(nums)):
            product = 1
            for j in range(i, len(nums)):
                product *= nums[j]
                res = max(res, product)
        return res
''',
    },
]

CLEAN_VARIANTS = []
