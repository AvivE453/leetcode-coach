from itertools import combinations

from evals.bank.controls import PRELUDE, external_code

NUMBER = 15
SLUG = "3sum"
TITLE = "3Sum"
DIFFICULTY = "Medium"
SPLIT = "dev"
METHOD = "threeSum"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    (([-1, 0, 1, 2, -1, -4],), [[-1, -1, 2], [-1, 0, 1]], "general"),
    (([0, 1, 1],), [], "general"),
    (([0, 0, 0, 0],), [[0, 0, 0]], "general"),
    (([-2, 0, 1, 1, 2],), [[-2, 0, 2], [-2, 1, 1]], "general"),
    (([0, 0, 0],), [[0, 0, 0]], "edge"),
]

SCALE = ([(i * 37) % 101 - 50 for i in range(250)],)
# Not the 3000 numbers the constraints allow: a quadratic solution under the memory tracer
# outlasts the oracle's timeout there.
SPACE_SCALE = ([(i * 7919) % 200_001 - 100_000 for i in range(1000)],)


def normalize(triplets):
    """LeetCode accepts the triplets, and the numbers in each, in any order."""
    return sorted(sorted(triplet) for triplet in triplets)


def reference(nums):
    return [list(triplet) for triplet in sorted({tuple(sorted(c)) for c in combinations(nums, 3) if sum(c) == 0})]


def generate(rng):
    # constraints: 3 <= nums.length <= 3000, -10^5 <= nums[i] <= 10^5
    return ([rng.randint(-3, 3) for _ in range(rng.randint(3, 8))],)


MUTANTS = [
    {
        "id": "repeats-a-duplicate-anchor",
        "mutation": "missing-guard",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def threeSum(self, nums: List[int]) -> List[List[int]]:
        res = []
        nums.sort()

        for i, a in enumerate(nums):
            # Skip positive integers
            if a > 0:
                break

            l, r = i + 1, len(nums) - 1
            while l < r:
                threeSum = a + nums[l] + nums[r]
                if threeSum > 0:
                    r -= 1
                elif threeSum < 0:
                    l += 1
                else:
                    res.append([a, nums[l], nums[r]])
                    l += 1
                    r -= 1
                    while nums[l] == nums[l - 1] and l < r:
                        l += 1

        return res
''',
    },
    {
        "id": "stops-at-a-zero-anchor",
        "mutation": "wrong-operator",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def threeSum(self, nums: List[int]) -> List[List[int]]:
        res = []
        nums.sort()

        for i, a in enumerate(nums):
            # Skip positive integers
            if a >= 0:
                break

            if i > 0 and a == nums[i - 1]:
                continue

            l, r = i + 1, len(nums) - 1
            while l < r:
                threeSum = a + nums[l] + nums[r]
                if threeSum > 0:
                    r -= 1
                elif threeSum < 0:
                    l += 1
                else:
                    res.append([a, nums[l], nums[r]])
                    l += 1
                    r -= 1
                    while nums[l] == nums[l - 1] and l < r:
                        l += 1

        return res
''',
    },
    {
        "id": "every-triple",
        "mutation": "brute-force",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def threeSum(self, nums: List[int]) -> List[List[int]]:
        found = set()
        for i in range(len(nums)):
            for j in range(i + 1, len(nums)):
                for k in range(j + 1, len(nums)):
                    if nums[i] + nums[j] + nums[k] == 0:
                        found.add(tuple(sorted((nums[i], nums[j], nums[k]))))
        return [list(triplet) for triplet in found]
''',
    },
]

CLEAN_VARIANTS = []
