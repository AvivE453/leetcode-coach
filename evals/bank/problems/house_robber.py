NUMBER = 198
SLUG = "house-robber"
TITLE = "House Robber"
DIFFICULTY = "Medium"

CANONICAL = '''\
class Solution:
    def rob(self, nums):
        skip, take = 0, 0
        for x in nums:
            skip, take = max(skip, take), skip + x
        return max(skip, take)
'''

TESTS = [
    (([1, 2, 3, 1],), 4, "general"),
    (([2, 7, 9, 3, 1],), 12, "general"),
    (([2, 1, 1, 2],), 4, "general"),
    # constraints: 1 <= nums.length
    (([5],), 5, "edge"),
]

SCALE = ([(i * 7919) % 101 for i in range(32)],)

MUTANTS = [
    {
        "id": "assumes-nonempty",
        "mutation": "missing-guard",
        "intended": "edge-case",
        "code": '''\
class Solution:
    def rob(self, nums):
        skip, take = 0, nums[0]
        for x in nums[1:]:
            skip, take = max(skip, take), skip + x
        return max(skip, take)
''',
    },
    {
        "id": "alternate-sums",
        "mutation": "greedy-substitution",
        "intended": "bug",
        "code": '''\
class Solution:
    def rob(self, nums):
        return max(sum(nums[0::2]), sum(nums[1::2]))
''',
    },
    {
        "id": "naive-recursion",
        "mutation": "naive-recursion",
        "intended": "complexity",
        "code": '''\
class Solution:
    def rob(self, nums):
        def best(i):
            if i >= len(nums):
                return 0
            return max(nums[i] + best(i + 2), best(i + 1))

        return best(0)
''',
    },
]

CLEAN_VARIANTS = [
    {
        "id": "best-up-to-previous-two",
        "control": "representative",
        "code": '''\
class Solution:
    def rob(self, nums):
        two_back = one_back = 0
        for x in nums:
            two_back, one_back = one_back, max(one_back, two_back + x)
        return one_back
''',
    },
    {
        "id": "seed-with-first-house",
        "control": "regression",
        "probes": "flagging an input the constraints exclude (1 <= nums.length)",
        "code": '''\
class Solution:
    def rob(self, nums):
        prev, best = 0, nums[0]
        for i in range(1, len(nums)):
            prev, best = best, max(best, prev + nums[i])
        return best
''',
    },
]
