from evals.bank.controls import PRELUDE, external_code

NUMBER = 239
SLUG = "sliding-window-maximum"
TITLE = "Sliding Window Maximum"
DIFFICULTY = "Hard"
SPLIT = "dev"
METHOD = "maxSlidingWindow"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    (([1, 3, -1, -3, 5, 3, 6, 7], 3), [3, 3, 5, 5, 6, 7], "general"),
    (([9, 11], 2), [11], "general"),
    (([4, -2], 2), [4], "general"),
    (([7, 2, 4], 2), [7, 4], "general"),
    (([1], 1), [1], "edge"),
    (([1, -1], 1), [1, -1], "edge"),
]

SCALE = ([(i * 7919) % 20011 for i in range(20_000)], 10_000)
SPACE_SCALE = ([(i * 7919) % 20011 for i in range(100_000)], 50_000)


def reference(nums, k):
    return [max(nums[i:i + k]) for i in range(len(nums) - k + 1)]


def generate(rng):
    # constraints: 1 <= nums.length <= 10^5, -10^4 <= nums[i] <= 10^4, 1 <= k <= nums.length
    nums = [rng.randint(-3, 3) for _ in range(rng.randint(1, 8))]
    return (nums, rng.randint(1, len(nums)))


MUTANTS = [
    {
        "id": "keeps-the-smaller-values",
        "mutation": "wrong-operator",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def maxSlidingWindow(self, nums: List[int], k: int) -> List[int]:
        output = []
        q = collections.deque()  # index
        l = r = 0
        # O(n) O(n)
        while r < len(nums):
            # pop smaller values from q
            while q and nums[q[-1]] > nums[r]:
                q.pop()
            q.append(r)

            # remove left val from window
            if l > q[0]:
                q.popleft()

            if (r + 1) >= k:
                output.append(nums[q[0]])
                l += 1
            r += 1

        return output
''',
    },
    {
        "id": "expired-maximum-never-leaves",
        "mutation": "missing-guard",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def maxSlidingWindow(self, nums: List[int], k: int) -> List[int]:
        output = []
        q = collections.deque()  # index
        l = r = 0
        # O(n) O(n)
        while r < len(nums):
            # pop smaller values from q
            while q and nums[q[-1]] < nums[r]:
                q.pop()
            q.append(r)

            if (r + 1) >= k:
                output.append(nums[q[0]])
                l += 1
            r += 1

        return output
''',
    },
    {
        "id": "max-of-every-window",
        "mutation": "brute-force",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def maxSlidingWindow(self, nums: List[int], k: int) -> List[int]:
        return [max(nums[i:i + k]) for i in range(len(nums) - k + 1)]
''',
    },
]

CLEAN_VARIANTS = []
