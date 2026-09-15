NUMBER = 1
SLUG = "two-sum"
TITLE = "Two Sum"
DIFFICULTY = "Easy"
SPLIT = "dev"
METHOD = "twoSum"

CANONICAL = '''\
class Solution:
    def twoSum(self, nums, target):
        seen = {}
        for i, x in enumerate(nums):
            if target - x in seen:
                return [seen[target - x], i]
            seen[x] = i
        return []
'''

TESTS = [
    (([2, 7, 11, 15], 9), [0, 1], "general"),
    (([3, 2, 4], 6), [1, 2], "general"),
    (([3, 3], 6), [0, 1], "edge"),
    (([1, 2], 3), [0, 1], "edge"),
]

SCALE = (list(range(3000)), 5997)
SPACE_SCALE = (list(range(10_000)), 19_997)


def normalize(pair):
    """LeetCode accepts the two indices in either order, and some solutions return a tuple."""
    return sorted(pair)


def reference(nums, target):
    for i in range(len(nums)):
        for j in range(i + 1, len(nums)):
            if nums[i] + nums[j] == target:
                return [i, j]


def generate(rng):
    # constraints: 2 <= nums.length <= 10^4, and exactly one pair adds up to target
    while True:
        nums = [rng.randint(-9, 9) for _ in range(rng.randint(2, 9))]
        i, j = rng.sample(range(len(nums)), 2)
        target = nums[i] + nums[j]
        pairs = sum(nums[a] + nums[b] == target for a in range(len(nums)) for b in range(a + 1, len(nums)))
        if pairs == 1:
            return (nums, target)

MUTANTS = [
    {
        "id": "nested-loop",
        "mutation": "brute-force",
        "intended": "complexity",
        "code": '''\
class Solution:
    def twoSum(self, nums, target):
        for i in range(len(nums)):
            for j in range(i + 1, len(nums)):
                if nums[i] + nums[j] == target:
                    return [i, j]
        return []
''',
    },
    {
        "id": "insert-before-check",
        "mutation": "off-by-one",
        "intended": "edge-case",
        "code": '''\
class Solution:
    def twoSum(self, nums, target):
        seen = {}
        for i, x in enumerate(nums):
            seen[x] = i
            if target - x in seen:
                return [seen[target - x], i]
        return []
''',
    },
]

CLEAN_VARIANTS = [
    {
        "id": "two-pass-hashmap",
        "control": "representative",
        "code": '''\
class Solution:
    def twoSum(self, nums, target):
        index = {x: i for i, x in enumerate(nums)}
        for i, x in enumerate(nums):
            j = index.get(target - x)
            if j is not None and j != i:
                return [i, j]
        return []
''',
    },
    {
        "id": "store-complement",
        "control": "representative",
        "code": '''\
class Solution:
    def twoSum(self, nums, target):
        wanted = {}
        for i, x in enumerate(nums):
            if x in wanted:
                return [wanted[x], i]
            wanted[target - x] = i
        return []
''',
    },
    {
        "id": "relies-on-guaranteed-answer",
        "control": "regression",
        "probes": "flagging an input the constraints exclude (exactly one answer is guaranteed)",
        "code": '''\
class Solution:
    def twoSum(self, nums, target):
        seen = {}
        for i, x in enumerate(nums):
            if target - x in seen:
                return [seen[target - x], i]
            seen[x] = i
''',
    },
]
