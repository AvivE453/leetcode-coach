from evals.bank.controls import PRELUDE, external_code

NUMBER = 930
SLUG = "binary-subarrays-with-sum"
TITLE = "Binary Subarrays With Sum"
DIFFICULTY = "Medium"
SPLIT = "test"
METHOD = "numSubarraysWithSum"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    (([1, 0, 1, 0, 1], 2), 4, "general"),
    (([0, 0, 0, 0, 0], 0), 15, "general"),
    (([1, 1, 1], 2), 2, "general"),
    (([0, 1, 0], 1), 4, "general"),
    (([1, 0, 0, 1], 3), 0, "general"),
    (([0], 0), 1, "edge"),
    (([1], 0), 0, "edge"),
    (([1], 1), 1, "edge"),
]

SCALE = ([1 if i % 3 == 0 else 0 for i in range(3000)], 50)
SPACE_SCALE = ([1 if i % 3 == 0 else 0 for i in range(3 * 10**4)], 500)


def reference(nums, goal):
    return sum(sum(nums[i:j]) == goal for i in range(len(nums)) for j in range(i + 1, len(nums) + 1))


def valid(nums, goal):
    # 1 <= nums.length <= 3 * 10^4, nums[i] is 0 or 1, 0 <= goal <= nums.length
    return 1 <= len(nums) <= 3 * 10**4 and set(nums) <= {0, 1} and 0 <= goal <= len(nums)


def generate(rng):
    nums = [rng.randint(0, 1) for _ in range(rng.randint(1, 10))]
    return (nums, rng.randint(0, len(nums)))


MUTANTS = [
    {
        "id": "no-empty-prefix-counted",
        "mutation": "wrong-init",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def numSubarraysWithSum(self, nums: List[int], goal: int) -> int:
        ans = 0
        prefix = 0
        count = collections.Counter()

        for num in nums:
            prefix += num
            ans += count[prefix - goal]
            count[prefix] += 1

        return ans
''',
    },
    {
        "id": "at-most-minus-one-unguarded",
        "mutation": "missing-guard",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def numSubarraysWithSum(self, nums: List[int], goal: int) -> int:

        def helper(x):
            res = 0
            l, cur = 0, 0
            for r in range(len(nums)):
                cur += nums[r]
                while cur > x:
                    cur -= nums[l]
                    l += 1
                res += (r - l + 1)
            return res

        return helper(goal) - helper(goal - 1)
''',
    },
    {
        "id": "sums-every-subarray",
        "mutation": "brute-force",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def numSubarraysWithSum(self, nums: List[int], goal: int) -> int:
        count = 0
        for i in range(len(nums)):
            total = 0
            for j in range(i, len(nums)):
                total += nums[j]
                if total == goal:
                    count += 1
        return count
''',
    },
]

CLEAN_VARIANTS = []
