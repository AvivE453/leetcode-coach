from evals.bank.controls import PRELUDE, external_code

NUMBER = 33
SLUG = "search-in-rotated-sorted-array"
TITLE = "Search in Rotated Sorted Array"
DIFFICULTY = "Medium"
SPLIT = "test"
METHOD = "search"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    (([4, 5, 6, 7, 0, 1, 2], 0), 4, "general"),
    (([4, 5, 6, 7, 0, 1, 2], 3), -1, "general"),
    (([4, 5, 6, 7, 0, 1, 2], 4), 0, "general"),
    (([5, 1, 3], 5), 0, "general"),
    (([3, 1], 1), 1, "general"),
    (([1, 3], 3), 1, "general"),
    (([1], 0), -1, "edge"),
    (([1], 1), 0, "edge"),
]

SCALE = (list(range(2500, 5000)) + list(range(2500)), 2499)
SPACE_SCALE = (list(range(2500, 5000)) + list(range(2500)), 2499)


def reference(nums, target):
    return nums.index(target) if target in nums else -1


def generate(rng):
    # constraints: 1 <= nums.length <= 5000, unique values, sorted ascending and then rotated
    values = sorted(rng.sample(range(-20, 20), rng.randint(1, 10)))
    k = rng.randrange(len(values))
    nums = values[k:] + values[:k]
    target = rng.choice(nums) if rng.random() < 0.6 else rng.randint(-25, 25)
    return (nums, target)


MUTANTS = [
    {
        "id": "strict-left-half-check",
        "mutation": "wrong-operator",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def search(self, nums: List[int], target: int) -> int:
        l, r = 0, len(nums) - 1

        while l <= r:
            mid = (l + r) // 2
            if target == nums[mid]:
                return mid

            # left sorted portion
            if nums[l] < nums[mid]:
                if target > nums[mid] or target < nums[l]:
                    l = mid + 1
                else:
                    r = mid - 1
            # right sorted portion
            else:
                if target < nums[mid] or target > nums[r]:
                    r = mid - 1
                else:
                    l = mid + 1
        return -1
''',
    },
    {
        "id": "left-bound-excludes-its-own-value",
        "mutation": "off-by-one",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def search(self, nums: List[int], target: int) -> int:
        l, r = 0, len(nums) - 1

        while l <= r:
            mid = (l + r) // 2
            if target == nums[mid]:
                return mid

            # left sorted portion
            if nums[l] <= nums[mid]:
                if target > nums[mid] or target <= nums[l]:
                    l = mid + 1
                else:
                    r = mid - 1
            # right sorted portion
            else:
                if target < nums[mid] or target > nums[r]:
                    r = mid - 1
                else:
                    l = mid + 1
        return -1
''',
    },
    {
        "id": "linear-scan",
        "mutation": "brute-force",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def search(self, nums: List[int], target: int) -> int:
        for i in range(len(nums)):
            if nums[i] == target:
                return i
        return -1
''',
    },
]

CLEAN_VARIANTS = []
