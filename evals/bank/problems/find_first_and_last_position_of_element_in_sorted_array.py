from evals.bank.controls import PRELUDE, external_code

NUMBER = 34
SLUG = "find-first-and-last-position-of-element-in-sorted-array"
TITLE = "Find First and Last Position of Element in Sorted Array"
DIFFICULTY = "Medium"
SPLIT = "test"
METHOD = "searchRange"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    (([5, 7, 7, 8, 8, 10], 8), [3, 4], "general"),
    (([5, 7, 7, 8, 8, 10], 6), [-1, -1], "general"),
    (([2, 2, 2, 2], 2), [0, 3], "general"),
    (([1, 3, 5], 5), [2, 2], "general"),
    (([1, 3, 5], 0), [-1, -1], "general"),
    (([], 0), [-1, -1], "edge"),
    (([1], 1), [0, 0], "edge"),
    (([1, 3, 5], 6), [-1, -1], "edge"),
]

SCALE = ([i // 3 for i in range(3000)], 700)
SPACE_SCALE = ([i // 3 for i in range(3000)], 700)


def reference(nums, target):
    found = [i for i, x in enumerate(nums) if x == target]
    return [found[0], found[-1]] if found else [-1, -1]


def normalize(answer):
    """LeetCode accepts the pair as a list or a tuple."""
    return list(answer)


def valid(nums, target):
    # 0 <= nums.length <= 10^5, -10^9 <= nums[i], target <= 10^9, nums is non-decreasing
    return (len(nums) <= 10**5 and all(-10**9 <= x <= 10**9 for x in nums) and nums == sorted(nums)
            and -10**9 <= target <= 10**9)


def generate(rng):
    nums = sorted(rng.randint(-5, 5) for _ in range(rng.randint(0, 10)))
    return (nums, rng.randint(-6, 6))


def is_edge(nums, target):
    return not nums or target > nums[-1]


MUTANTS = [
    {
        "id": "biases-swapped",
        "mutation": "wrong-operator",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def searchRange(self, nums: List[int], target: int) -> List[int]:
        left = self.binSearch(nums, target, True)
        right = self.binSearch(nums, target, False)
        return [left, right]

    def binSearch(self, nums, target, leftBias):
        l, r = 0, len(nums) - 1
        i = -1
        while l <= r:
            m = (l + r) // 2
            if target > nums[m]:
                l = m + 1
            elif target < nums[m]:
                r = m - 1
            else:
                i = m
                if leftBias:
                    l = m + 1
                else:
                    r = m - 1
        return i
''',
    },
    {
        "id": "reads-past-the-end",
        "mutation": "missing-guard",
        "intended": "edge-case",
        "code": PRELUDE + '''\
class Solution:
    def searchRange(self, nums: List[int], target: int) -> List[int]:
        l = bisect_left(nums, target)
        if nums[l] != target:
            return [-1, -1]
        r = bisect_right(nums, target) - 1
        return [l, r]
''',
    },
    {
        "id": "scans-for-the-target",
        "mutation": "brute-force",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def searchRange(self, nums: List[int], target: int) -> List[int]:
        first = last = -1
        for i, num in enumerate(nums):
            if num == target:
                if first == -1:
                    first = i
                last = i
        return [first, last]
''',
    },
]

CLEAN_VARIANTS = []
