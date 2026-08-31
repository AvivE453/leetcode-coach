NUMBER = 217
SLUG = "contains-duplicate"
TITLE = "Contains Duplicate"
DIFFICULTY = "Easy"

CANONICAL = '''\
class Solution:
    def containsDuplicate(self, nums):
        seen = set()
        for x in nums:
            if x in seen:
                return True
            seen.add(x)
        return False
'''

TESTS = [
    (([1, 2, 3, 1],), True, "general"),
    (([1, 2, 3, 4],), False, "general"),
    (([1, 1, 1, 3, 3, 4, 3, 2, 4, 2],), True, "general"),
    # constraints: 1 <= nums.length, so an empty array is not a valid input
    (([7],), False, "edge"),
]

SCALE = (list(range(3000)),)

MUTANTS = [
    {
        "id": "nested-loop",
        "mutation": "brute-force",
        "intended": "complexity",
        "code": '''\
class Solution:
    def containsDuplicate(self, nums):
        for i in range(len(nums)):
            for j in range(i + 1, len(nums)):
                if nums[i] == nums[j]:
                    return True
        return False
''',
    },
    {
        "id": "assumes-nonempty",
        "mutation": "missing-guard",
        "intended": "edge-case",
        "code": '''\
class Solution:
    def containsDuplicate(self, nums):
        seen = {nums[0]}
        for x in nums[1:]:
            if x in seen:
                return True
            seen.add(x)
        return False
''',
    },
    {
        "id": "adjacent-only",
        "mutation": "missing-precondition",
        "intended": "bug",
        "code": '''\
class Solution:
    def containsDuplicate(self, nums):
        for i in range(1, len(nums)):
            if nums[i] == nums[i - 1]:
                return True
        return False
''',
    },
]
