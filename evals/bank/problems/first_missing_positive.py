from itertools import count

from evals.bank.controls import PRELUDE, external_code

NUMBER = 41
SLUG = "first-missing-positive"
TITLE = "First Missing Positive"
DIFFICULTY = "Hard"
SPLIT = "test"
METHOD = "firstMissingPositive"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    (([1, 2, 0],), 3, "general"),
    (([3, 4, -1, 1],), 2, "general"),
    (([7, 8, 9, 11, 12],), 1, "general"),
    (([2, 2],), 1, "general"),
    (([0, -1, 3, 1],), 2, "general"),
    (([-1, 2],), 1, "general"),
    (([-2**31, 2**31 - 1],), 1, "general"),
    (([1],), 2, "edge"),
    (([2, 1, 3],), 4, "edge"),
]

# Every number from 1 to 3000, so the answer is 3001 and nothing ends early.
SCALE = ([(i * 7) % 3000 + 1 for i in range(3000)],)
SPACE_SCALE = ([(i * 7) % 3000 + 1 for i in range(3000)],)


def reference(nums):
    present = set(nums)
    return next(i for i in count(1) if i not in present)


def valid(nums):
    # 1 <= nums.length <= 10^5, -2^31 <= nums[i] <= 2^31 - 1
    return 1 <= len(nums) <= 10**5 and all(-2**31 <= x <= 2**31 - 1 for x in nums)


def generate(rng):
    n = rng.randint(1, 8)
    if rng.random() < 0.25:
        nums = list(range(1, n + 1))
        rng.shuffle(nums)
        return (nums,)
    return ([rng.randint(-3, 9) for _ in range(n)],)


def is_edge(nums):
    return sorted(nums) == list(range(1, len(nums) + 1))


MUTANTS = [
    {
        "id": "keeps-the-negatives",
        "mutation": "missing-precondition",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def firstMissingPositive(self, nums: List[int]) -> int:
        A = nums
        for i in range(len(A)):
            val = abs(A[i])
            if 1 <= val <= len(A):
                if A[val - 1] > 0:
                    A[val - 1] *= -1
                elif A[val - 1] == 0:
                    A[val - 1] = -1 * (len(A) + 1)

        for i in range(1, len(A) + 1):
            if A[i - 1] >= 0:
                return i

        return len(A) + 1
''',
    },
    {
        "id": "no-answer-past-the-array",
        "mutation": "missing-guard",
        "intended": "edge-case",
        "code": PRELUDE + '''\
class Solution:
    def firstMissingPositive(self, nums: List[int]) -> int:
        A = nums
        for i in range(len(A)):
            if A[i] < 0:
                A[i] = 0

        for i in range(len(A)):
            val = abs(A[i])
            if 1 <= val <= len(A):
                if A[val - 1] > 0:
                    A[val - 1] *= -1
                elif A[val - 1] == 0:
                    A[val - 1] = -1 * (len(A) + 1)

        for i in range(1, len(A) + 1):
            if A[i - 1] >= 0:
                return i
''',
    },
    {
        "id": "searches-the-list-for-each-candidate",
        "mutation": "brute-force",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def firstMissingPositive(self, nums: List[int]) -> int:
        i = 1
        while i in nums:
            i += 1
        return i
''',
    },
]

CLEAN_VARIANTS = []
