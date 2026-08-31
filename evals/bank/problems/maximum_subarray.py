NUMBER = 53
SLUG = "maximum-subarray"
TITLE = "Maximum Subarray"
DIFFICULTY = "Medium"

CANONICAL = '''\
class Solution:
    def maxSubArray(self, nums):
        cur = best = nums[0]
        for i in range(1, len(nums)):
            cur = max(nums[i], cur + nums[i])
            best = max(best, cur)
        return best
'''

TESTS = [
    (([-2, 1, -3, 4, -1, 2, 1, -5, 4],), 6, "general"),
    (([5, 4, -1, 7, 8],), 23, "general"),
    (([-3, -1, -2],), -1, "edge"),
    (([1],), 1, "edge"),
    (([-1],), -1, "edge"),
]

SCALE = ([(-1) ** i * (i % 17) for i in range(250)],)

MUTANTS = [
    {
        "id": "zero-init",
        "mutation": "wrong-init",
        "intended": "edge-case",
        "code": '''\
class Solution:
    def maxSubArray(self, nums):
        cur = best = 0
        for x in nums:
            cur = max(0, cur + x)
            best = max(best, cur)
        return best
''',
    },
    {
        "id": "brute-force",
        "mutation": "brute-force",
        "intended": "complexity",
        "code": '''\
class Solution:
    def maxSubArray(self, nums):
        best = nums[0]
        for i in range(len(nums)):
            for j in range(i, len(nums)):
                best = max(best, sum(nums[i:j + 1]))
        return best
''',
    },
]
