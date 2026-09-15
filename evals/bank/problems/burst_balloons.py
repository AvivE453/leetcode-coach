from itertools import permutations

from evals.bank.controls import PRELUDE, external_code

NUMBER = 312
SLUG = "burst-balloons"
TITLE = "Burst Balloons"
DIFFICULTY = "Hard"
SPLIT = "test"
METHOD = "maxCoins"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    (([3, 1, 5, 8],), 167, "general"),
    (([1, 5],), 10, "general"),
    (([2, 3],), 9, "general"),
    (([7],), 7, "edge"),
]

SCALE = ([(i * 7) % 10 + 1 for i in range(12)],)
# Not the 300 balloons the constraints allow: the canonical is cubic, and at 300 one call
# outlasts the oracle's timeout. A hundred still separates O(n^2) memory from O(n^3).
SPACE_SCALE = ([(i * 37) % 101 for i in range(100)],)
DIFFERENTIAL_CASES = 300


def reference(nums):
    best = 0
    for order in permutations(range(len(nums))):
        alive = list(range(len(nums)))
        coins = 0
        for index in order:
            position = alive.index(index)
            left = nums[alive[position - 1]] if position > 0 else 1
            right = nums[alive[position + 1]] if position + 1 < len(alive) else 1
            coins += left * nums[index] * right
            alive.pop(position)
        best = max(best, coins)
    return best


def generate(rng):
    # constraints: 1 <= nums.length <= 300, 0 <= nums[i] <= 100
    return ([rng.randint(0, 9) for _ in range(rng.randint(1, 6))],)


MUTANTS = [
    {
        "id": "burst-the-smallest-first",
        "mutation": "greedy-substitution",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def maxCoins(self, nums: List[int]) -> int:
        nums = [1] + nums + [1]
        coins = 0
        while len(nums) > 2:
            i = min(range(1, len(nums) - 1), key=lambda k: nums[k])
            coins += nums[i - 1] * nums[i] * nums[i + 1]
            nums.pop(i)
        return coins
''',
    },
    {
        "id": "last-pivot-never-tried",
        "mutation": "off-by-one",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def maxCoins(self, nums: List[int]) -> int:
        cache = {}
        nums = [1] + nums + [1]

        for offset in range(2, len(nums)):
            for left in range(len(nums) - offset):
                right = left + offset
                for pivot in range(left + 1, right - 1):
                    coins = nums[left] * nums[pivot] * nums[right]
                    coins += cache.get((left, pivot), 0) + cache.get((pivot, right), 0)
                    cache[(left, right)] = max(coins, cache.get((left, right), 0))
        return cache.get((0, len(nums) - 1), 0)
''',
    },
    {
        "id": "recursion-without-memo",
        "mutation": "naive-recursion",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def maxCoins(self, nums: List[int]) -> int:
        nums = [1] + nums + [1]

        def best(left, right):
            return max((nums[left] * nums[pivot] * nums[right] + best(left, pivot) + best(pivot, right)
                        for pivot in range(left + 1, right)), default=0)

        return best(0, len(nums) - 1)
''',
    },
]

CLEAN_VARIANTS = []
