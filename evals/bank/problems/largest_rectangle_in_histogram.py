from evals.bank.controls import PRELUDE, external_code

NUMBER = 84
SLUG = "largest-rectangle-in-histogram"
TITLE = "Largest Rectangle in Histogram"
DIFFICULTY = "Hard"
SPLIT = "dev"
METHOD = "largestRectangleArea"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    (([2, 1, 5, 6, 2, 3],), 10, "general"),
    (([2, 4],), 4, "general"),
    (([2, 1, 2],), 3, "general"),
    (([1, 1],), 2, "general"),
    (([1],), 1, "edge"),
    (([0],), 0, "edge"),
]

SCALE = ([(i * 7919) % 101 for i in range(3000)],)
SPACE_SCALE = ([(i * 7919) % 10001 for i in range(100_000)],)


def reference(heights):
    return max(min(heights[i:j + 1]) * (j - i + 1) for i in range(len(heights)) for j in range(i, len(heights)))


def generate(rng):
    # constraints: 1 <= heights.length <= 10^5, 0 <= heights[i] <= 10^4
    return ([rng.randint(0, 5) for _ in range(rng.randint(1, 8))],)


MUTANTS = [
    {
        "id": "popped-bars-do-not-extend-left",
        "mutation": "missing-precondition",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def largestRectangleArea(self, heights: List[int]) -> int:
        maxArea = 0
        stack = []  # pair: (index, height)

        for i, h in enumerate(heights):
            while stack and stack[-1][1] > h:
                index, height = stack.pop()
                maxArea = max(maxArea, height * (i - index))
            stack.append((i, h))

        for i, h in stack:
            maxArea = max(maxArea, h * (len(heights) - i))
        return maxArea
''',
    },
    {
        "id": "remaining-bars-one-short",
        "mutation": "off-by-one",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def largestRectangleArea(self, heights: List[int]) -> int:
        maxArea = 0
        stack = []  # pair: (index, height)

        for i, h in enumerate(heights):
            start = i
            while stack and stack[-1][1] > h:
                index, height = stack.pop()
                maxArea = max(maxArea, height * (i - index))
                start = index
            stack.append((start, h))

        for i, h in stack:
            maxArea = max(maxArea, h * (len(heights) - i - 1))
        return maxArea
''',
    },
    {
        "id": "every-range",
        "mutation": "brute-force",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def largestRectangleArea(self, heights: List[int]) -> int:
        maxArea = 0
        for i in range(len(heights)):
            low = heights[i]
            for j in range(i, len(heights)):
                low = min(low, heights[j])
                maxArea = max(maxArea, low * (j - i + 1))
        return maxArea
''',
    },
]

CLEAN_VARIANTS = []
