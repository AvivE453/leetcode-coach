from evals.bank.controls import PRELUDE, external_code

NUMBER = 128
SLUG = "longest-consecutive-sequence"
TITLE = "Longest Consecutive Sequence"
DIFFICULTY = "Medium"
SPLIT = "test"
METHOD = "longestConsecutive"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    (([100, 4, 200, 1, 3, 2],), 4, "general"),
    (([0, 3, 7, 2, 5, 8, 4, 6, 0, 1],), 9, "general"),
    (([1, 2, 0, 1],), 3, "general"),
    (([9, 1, -3, 10, 4, 20, 2],), 2, "general"),
    (([],), 0, "edge"),
    (([5],), 1, "edge"),
]

SCALE = ([0] * 2000 + list(range(2000)),)
SPACE_SCALE = (list(range(100_000)),)


def reference(nums):
    values = set(nums)
    best = 0
    for x in values:
        length = 0
        while x + length in values:
            length += 1
        best = max(best, length)
    return best


def generate(rng):
    # constraints: 0 <= nums.length <= 10^5, -10^9 <= nums[i] <= 10^9
    return ([rng.randint(-5, 5) for _ in range(rng.randint(0, 10))],)


def is_edge(nums):
    return not nums


MUTANTS = [
    {
        "id": "skips-the-next-number",
        "mutation": "off-by-one",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def longestConsecutive(self, nums: List[int]) -> int:
        numSet = set(nums)
        longest = 0

        for n in numSet:
            # check if its the start of a sequence
            if (n - 1) not in numSet:
                length = 1
                while (n + length + 1) in numSet:
                    length += 1
                longest = max(length, longest)
        return longest
''',
    },
    {
        "id": "longest-starts-at-one",
        "mutation": "wrong-init",
        "intended": "edge-case",
        "code": PRELUDE + '''\
class Solution:
    def longestConsecutive(self, nums: List[int]) -> int:
        numSet = set(nums)
        longest = 1

        for n in numSet:
            # check if its the start of a sequence
            if (n - 1) not in numSet:
                length = 1
                while (n + length) in numSet:
                    length += 1
                longest = max(length, longest)
        return longest
''',
    },
    {
        "id": "walks-every-duplicate",
        "mutation": "missing-precondition",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def longestConsecutive(self, nums: List[int]) -> int:
        numSet = set(nums)
        longest = 0

        for n in nums:
            # check if its the start of a sequence
            if (n - 1) not in numSet:
                length = 1
                while (n + length) in numSet:
                    length += 1
                longest = max(length, longest)
        return longest
''',
    },
]

CLEAN_VARIANTS = []
