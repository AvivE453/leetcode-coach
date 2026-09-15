from evals.bank.controls import PRELUDE, external_code

NUMBER = 42
SLUG = "trapping-rain-water"
TITLE = "Trapping Rain Water"
DIFFICULTY = "Hard"
SPLIT = "test"
METHOD = "trap"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    (([0, 1, 0, 2, 1, 0, 1, 3, 2, 1, 2, 1],), 6, "general"),
    (([4, 2, 0, 3, 2, 5],), 9, "general"),
    (([5, 4, 1, 2],), 1, "general"),
    (([2, 0, 2],), 2, "general"),
    (([3],), 0, "edge"),
    (([1, 2],), 0, "edge"),
]

SCALE = ([(i * 7919) % 101 for i in range(5000)],)
SPACE_SCALE = ([(i * 7919) % 100_001 for i in range(20_000)],)


def reference(height):
    return sum(min(max(height[:i + 1]), max(height[i:])) - h for i, h in enumerate(height))


def generate(rng):
    # constraints: 1 <= height.length <= 2 * 10^4, 0 <= height[i] <= 10^5
    return ([rng.randint(0, 5) for _ in range(rng.randint(1, 10))],)


MUTANTS = [
    {
        "id": "moves-the-higher-wall",
        "mutation": "wrong-operator",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def trap(self, height: List[int]) -> int:
        if not height:
            return 0

        l, r = 0, len(height) - 1
        leftMax, rightMax = height[l], height[r]
        res = 0
        while l < r:
            if leftMax > rightMax:
                l += 1
                leftMax = max(leftMax, height[l])
                res += leftMax - height[l]
            else:
                r -= 1
                rightMax = max(rightMax, height[r])
                res += rightMax - height[r]
        return res
''',
    },
    {
        "id": "water-counted-before-the-wall-rises",
        "mutation": "off-by-one",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def trap(self, height: List[int]) -> int:
        if not height:
            return 0

        l, r = 0, len(height) - 1
        leftMax, rightMax = height[l], height[r]
        res = 0
        while l < r:
            if leftMax < rightMax:
                l += 1
                res += leftMax - height[l]
                leftMax = max(leftMax, height[l])
            else:
                r -= 1
                res += rightMax - height[r]
                rightMax = max(rightMax, height[r])
        return res
''',
    },
    {
        "id": "rescan-both-sides-per-bar",
        "mutation": "brute-force",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def trap(self, height: List[int]) -> int:
        res = 0
        for i in range(len(height)):
            leftMax = max(height[:i + 1])
            rightMax = max(height[i:])
            res += min(leftMax, rightMax) - height[i]
        return res
''',
    },
]

CLEAN_VARIANTS = []
