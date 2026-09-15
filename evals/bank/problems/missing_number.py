from evals.bank.controls import PRELUDE, external_code

NUMBER = 268
SLUG = "missing-number"
TITLE = "Missing Number"
DIFFICULTY = "Easy"
SPLIT = "dev"
METHOD = "missingNumber"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    (([3, 0, 1],), 2, "general"),
    (([0, 1],), 2, "general"),
    (([9, 6, 4, 2, 3, 5, 7, 0, 1],), 8, "general"),
    (([0],), 1, "edge"),
    (([1],), 0, "edge"),
]

SCALE = (list(range(10_000)),)
SPACE_SCALE = (list(range(10_000)),)


def reference(nums):
    return next(x for x in range(len(nums) + 1) if x not in nums)


def generate(rng):
    # constraints: 1 <= n <= 10^4, the n numbers are distinct and in [0, n]
    values = list(range(rng.randint(2, 11)))
    values.pop(rng.randrange(len(values)))
    rng.shuffle(values)
    return (values,)


MUTANTS = [
    {
        "id": "starts-from-n-minus-one",
        "mutation": "off-by-one",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def missingNumber(self, nums: List[int]) -> int:
        res = len(nums) - 1

        for i in range(len(nums)):
            res += i - nums[i]
        return res
''',
    },
    {
        "id": "check-each-candidate",
        "mutation": "brute-force",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def missingNumber(self, nums: List[int]) -> int:
        for x in range(len(nums) + 1):
            if x not in nums:
                return x
''',
    },
]

CLEAN_VARIANTS = []
