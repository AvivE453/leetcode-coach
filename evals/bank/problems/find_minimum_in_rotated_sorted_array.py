NUMBER = 153
SLUG = "find-minimum-in-rotated-sorted-array"
TITLE = "Find Minimum in Rotated Sorted Array"
DIFFICULTY = "Medium"

CANONICAL = '''\
class Solution:
    def findMin(self, nums):
        lo, hi = 0, len(nums) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if nums[mid] > nums[hi]:
                lo = mid + 1
            else:
                hi = mid
        return nums[lo]
'''

TESTS = [
    (([3, 4, 5, 1, 2],), 1, "general"),
    (([4, 5, 6, 7, 0, 1, 2],), 0, "general"),
    (([11, 13, 15, 17],), 11, "general"),
    (([2, 1],), 1, "general"),
    (([1],), 1, "edge"),
]

SCALE = (list(range(500, 2000)) + list(range(500)),)

MUTANTS = [
    {
        "id": "inclusive-bound",
        "mutation": "wrong-operator",
        "intended": "bug",
        "code": '''\
class Solution:
    def findMin(self, nums):
        lo, hi = 0, len(nums) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            if nums[mid] > nums[hi]:
                lo = mid + 1
            else:
                hi = mid
        return nums[lo]
''',
    },
    {
        "id": "compare-to-low",
        "mutation": "wrong-operator",
        "intended": "bug",
        "code": '''\
class Solution:
    def findMin(self, nums):
        lo, hi = 0, len(nums) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if nums[mid] > nums[lo]:
                lo = mid + 1
            else:
                hi = mid
        return nums[lo]
''',
    },
]

CLEAN_VARIANTS = [
    {
        "id": "stop-once-sorted",
        "control": "representative",
        "code": '''\
class Solution:
    def findMin(self, nums):
        lo, hi = 0, len(nums) - 1
        while lo < hi:
            if nums[lo] < nums[hi]:
                return nums[lo]
            mid = (lo + hi) // 2
            if nums[mid] >= nums[lo]:
                lo = mid + 1
            else:
                hi = mid
        return nums[lo]
''',
    },
    {
        "id": "first-not-above-last",
        "control": "representative",
        "code": '''\
class Solution:
    def findMin(self, nums):
        lo, hi = 0, len(nums) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            if nums[mid] <= nums[-1]:
                hi = mid - 1
            else:
                lo = mid + 1
        return nums[lo]
''',
    },
]
