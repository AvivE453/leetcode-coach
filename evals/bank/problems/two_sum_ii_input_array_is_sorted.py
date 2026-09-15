from evals.bank.controls import PRELUDE, external_code

NUMBER = 167
SLUG = "two-sum-ii-input-array-is-sorted"
TITLE = "Two Sum II - Input Array Is Sorted"
DIFFICULTY = "Medium"
SPLIT = "dev"
METHOD = "twoSum"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    (([2, 7, 11, 15], 9), [1, 2], "general"),
    (([2, 3, 4], 6), [1, 3], "general"),
    (([1, 2, 3, 4, 4, 9, 56, 90], 8), [4, 5], "general"),
    (([5, 25, 75], 100), [2, 3], "general"),
    (([-1, 0], -1), [1, 2], "edge"),
]

SCALE = (list(range(3000)), 5997)
SPACE_SCALE = (list(range(30_000)), 59_997)


def reference(numbers, target):
    for i in range(len(numbers)):
        for j in range(i + 1, len(numbers)):
            if numbers[i] + numbers[j] == target:
                return [i + 1, j + 1]


def generate(rng):
    # constraints: 2 <= numbers.length <= 3 * 10^4, sorted non-decreasing, exactly one solution
    while True:
        numbers = sorted(rng.randint(-5, 5) for _ in range(rng.randint(2, 8)))
        i, j = rng.sample(range(len(numbers)), 2)
        target = numbers[i] + numbers[j]
        pairs = sum(numbers[a] + numbers[b] == target
                    for a in range(len(numbers)) for b in range(a + 1, len(numbers)))
        if pairs == 1:
            return (numbers, target)


MUTANTS = [
    {
        "id": "zero-based-answer",
        "mutation": "off-by-one",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def twoSum(self, numbers: List[int], target: int) -> List[int]:
        l, r = 0, len(numbers) - 1

        while l < r:
            curSum = numbers[l] + numbers[r]

            if curSum > target:
                r -= 1
            elif curSum < target:
                l += 1
            else:
                return [l, r]
''',
    },
    {
        "id": "moves-the-wrong-pointer",
        "mutation": "wrong-operator",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def twoSum(self, numbers: List[int], target: int) -> List[int]:
        l, r = 0, len(numbers) - 1

        while l < r:
            curSum = numbers[l] + numbers[r]

            if curSum > target:
                l += 1
            elif curSum < target:
                r -= 1
            else:
                return [l + 1, r + 1]
''',
    },
    {
        "id": "every-pair",
        "mutation": "brute-force",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def twoSum(self, numbers: List[int], target: int) -> List[int]:
        for i in range(len(numbers)):
            for j in range(i + 1, len(numbers)):
                if numbers[i] + numbers[j] == target:
                    return [i + 1, j + 1]
''',
    },
]

CLEAN_VARIANTS = []
