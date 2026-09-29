from evals.bank.controls import PRELUDE, external_code

NUMBER = 862
SLUG = "shortest-subarray-with-sum-at-least-k"
TITLE = "Shortest Subarray with Sum at Least K"
DIFFICULTY = "Hard"
SPLIT = "test"
METHOD = "shortestSubarray"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    (([1], 1), 1, "general"),
    (([1, 2], 4), -1, "general"),
    (([2, -1, 2], 3), 3, "general"),
    (([2, -1, 2, 1], 3), 2, "general"),
    (([84, -37, 32, 40, 95], 167), 3, "general"),
    (([-28, 81, -20, 28, -29], 89), 3, "general"),
    (([5], 10), -1, "edge"),
    (([-5], 1), -1, "edge"),
]

SCALE = ([(i * 37) % 21 - 8 for i in range(3000)], 200)
SPACE_SCALE = ([(i * 37) % 21 - 8 for i in range(10**5)], 5000)


def reference(nums, k):
    lengths = [j - i for i in range(len(nums)) for j in range(i + 1, len(nums) + 1) if sum(nums[i:j]) >= k]
    return min(lengths, default=-1)


def valid(nums, k):
    # 1 <= nums.length <= 10^5, -10^5 <= nums[i] <= 10^5, 1 <= k <= 10^9
    return 1 <= len(nums) <= 10**5 and all(-10**5 <= x <= 10**5 for x in nums) and 1 <= k <= 10**9


def generate(rng):
    return ([rng.randint(-5, 5) for _ in range(rng.randint(1, 8))], rng.randint(1, 10))


MUTANTS = [
    {
        "id": "sliding-window-over-negatives",
        "mutation": "greedy-substitution",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def shortestSubarray(self, nums: List[int], k: int) -> int:
        best = len(nums) + 1
        total = 0
        l = 0
        for r, num in enumerate(nums):
            total += num
            while total >= k and l <= r:
                best = min(best, r - l + 1)
                total -= nums[l]
                l += 1
        return best if best <= len(nums) else -1
''',
    },
    {
        "id": "queue-never-kept-increasing",
        "mutation": "missing-guard",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def shortestSubarray(self, nums: List[int], k: int) -> int:
        size = len(nums)
        pre = [0]
        for i in nums:
            pre.append(pre[-1] + i)

        ans = size + 1
        monoq = collections.deque()
        for i, val in enumerate(pre):
            while monoq and val - pre[monoq[0]] >= k:
                ans = min(ans, i - monoq.popleft())

            monoq.append(i)

        return ans if ans < size + 1 else -1
''',
    },
    {
        "id": "sums-every-subarray",
        "mutation": "brute-force",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def shortestSubarray(self, nums: List[int], k: int) -> int:
        best = len(nums) + 1
        for i in range(len(nums)):
            total = 0
            for j in range(i, len(nums)):
                total += nums[j]
                if total >= k:
                    best = min(best, j - i + 1)
                    break
        return best if best <= len(nums) else -1
''',
    },
]

CLEAN_VARIANTS = []
