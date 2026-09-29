from itertools import combinations, pairwise

from evals.bank.controls import PRELUDE, external_code

NUMBER = 410
SLUG = "split-array-largest-sum"
TITLE = "Split Array Largest Sum"
DIFFICULTY = "Hard"
SPLIT = "test"
METHOD = "splitArray"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    (([7, 2, 5, 10, 8], 2), 18, "general"),
    (([1, 2, 3, 4, 5], 2), 9, "general"),
    (([1, 4, 4], 3), 4, "general"),
    (([2, 2, 2, 2], 2), 4, "general"),
    (([5], 1), 5, "edge"),
    (([3, 1, 2], 1), 6, "edge"),
    (([0, 5], 2), 5, "edge"),
]

SCALE = ([(i * 7919) % 1_000_001 for i in range(1000)], 50)
SPACE_SCALE = ([(i * 7919) % 1_000_001 for i in range(1000)], 50)


def reference(nums, k):
    def largest(cuts):
        bounds = [0, *cuts, len(nums)]
        return max(sum(nums[a:b]) for a, b in pairwise(bounds))

    return min(largest(cuts) for cuts in combinations(range(1, len(nums)), k - 1))


def valid(nums, k):
    # 1 <= nums.length <= 1000, 0 <= nums[i] <= 10^6, 1 <= k <= min(50, nums.length)
    return 1 <= len(nums) <= 1000 and all(0 <= x <= 10**6 for x in nums) and 1 <= k <= min(50, len(nums))


def generate(rng):
    nums = [rng.randint(0, 10) for _ in range(rng.randint(1, 8))]
    return (nums, rng.randint(1, len(nums)))


def is_edge(nums, k):
    # The whole array is the answer: one subarray, or one number carrying all the sum.
    return k == 1 or sum(nums) == max(nums)


MUTANTS = [
    {
        "id": "splits-on-an-exact-fit",
        "mutation": "wrong-operator",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def splitArray(self, nums: List[int], m: int) -> int:
        def canSplit(largest):
            subarray = 0
            curSum = 0
            for n in nums:
                curSum += n
                if curSum >= largest:
                    subarray += 1
                    curSum = n
            return subarray + 1 <= m

        l, r = max(nums), sum(nums)
        res = r
        while l <= r:
            mid = l + ((r - l) // 2)
            if canSplit(mid):
                res = mid
                r = mid - 1
            else:
                l = mid + 1
        return res
''',
    },
    {
        "id": "upper-bound-below-the-total",
        "mutation": "off-by-one",
        "intended": "edge-case",
        "code": PRELUDE + '''\
class Solution:
    def splitArray(self, nums: List[int], m: int) -> int:
        def canSplit(largest):
            subarray = 0
            curSum = 0
            for n in nums:
                curSum += n
                if curSum > largest:
                    subarray += 1
                    curSum = n
            return subarray + 1 <= m

        l, r = max(nums), sum(nums) - 1
        res = r
        while l <= r:
            mid = l + ((r - l) // 2)
            if canSplit(mid):
                res = mid
                r = mid - 1
            else:
                l = mid + 1
        return res
''',
    },
    {
        "id": "tries-every-largest-sum",
        "mutation": "brute-force",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def splitArray(self, nums: List[int], k: int) -> int:
        for largest in range(max(nums), sum(nums) + 1):
            pieces, current = 1, 0
            for num in nums:
                if current + num > largest:
                    pieces += 1
                    current = 0
                current += num
            if pieces <= k:
                return largest
''',
    },
]

CLEAN_VARIANTS = []
