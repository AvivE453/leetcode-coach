from evals.bank.controls import PRELUDE, external_code

NUMBER = 11
SLUG = "container-with-most-water"
TITLE = "Container With Most Water"
DIFFICULTY = "Medium"
SPLIT = "test"
METHOD = "maxArea"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    (([1, 8, 6, 2, 5, 4, 8, 3, 7],), 49, "general"),
    (([4, 3, 2, 1, 4],), 16, "general"),
    (([1, 2, 1],), 2, "general"),
    (([1, 5, 5, 1],), 5, "general"),
    (([1, 1],), 1, "edge"),
    (([0, 0],), 0, "edge"),
]

SCALE = ([(i * 7919) % 10001 for i in range(3000)],)
SPACE_SCALE = ([(i * 7919) % 10001 for i in range(100_000)],)


def reference(height):
    return max(min(height[i], height[j]) * (j - i)
               for i in range(len(height)) for j in range(i + 1, len(height)))


def generate(rng):
    # constraints: 2 <= height.length <= 10^5, 0 <= height[i] <= 10^4
    return ([rng.randint(0, 10) for _ in range(rng.randint(2, 10))],)


MUTANTS = [
    {
        "id": "move-the-taller-side",
        "mutation": "greedy-substitution",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def maxArea(self, height: List[int]) -> int:
        l, r = 0, len(height) - 1
        res = 0

        while l < r:
            res = max(res, min(height[l], height[r]) * (r - l))
            if height[l] > height[r]:
                l += 1
            else:
                r -= 1

        return res
''',
    },
    {
        "id": "width-counts-both-ends",
        "mutation": "off-by-one",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def maxArea(self, height: List[int]) -> int:
        l, r = 0, len(height) - 1
        res = 0

        while l < r:
            res = max(res, min(height[l], height[r]) * (r - l + 1))
            if height[l] < height[r]:
                l += 1
            elif height[r] <= height[l]:
                r -= 1

        return res
''',
    },
    {
        "id": "every-pair",
        "mutation": "brute-force",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def maxArea(self, height: List[int]) -> int:
        res = 0
        for l in range(len(height)):
            for r in range(l + 1, len(height)):
                res = max(res, min(height[l], height[r]) * (r - l))
        return res
''',
    },
]

CLEAN_VARIANTS = []
