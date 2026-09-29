from evals.bank.controls import PRELUDE, external_code

NUMBER = 2001
SLUG = "number-of-pairs-of-interchangeable-rectangles"
TITLE = "Number of Pairs of Interchangeable Rectangles"
DIFFICULTY = "Medium"
SPLIT = "test"
METHOD = "interchangeableRectangles"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    (([[4, 8], [3, 6], [10, 20], [15, 30]],), 6, "general"),
    (([[4, 5], [7, 8]],), 0, "general"),
    (([[2, 4], [1, 2], [3, 6], [4, 2]],), 3, "general"),
    (([[1, 3], [2, 6], [3, 1], [6, 2]],), 2, "general"),
    (([[1, 1]],), 0, "edge"),
]

SCALE = ([[(i % 50) + 1, (i % 70) + 1] for i in range(3000)],)
SPACE_SCALE = ([[(i % 50) + 1, (i % 70) + 1] for i in range(10**5)],)


def reference(rectangles):
    return sum(w1 * h2 == w2 * h1
               for i, (w1, h1) in enumerate(rectangles) for w2, h2 in rectangles[i + 1:])


def valid(rectangles):
    # 1 <= n <= 10^5, rectangles[i].length == 2, 1 <= width, height <= 10^5
    return 1 <= len(rectangles) <= 10**5 and all(
        len(r) == 2 and 1 <= r[0] <= 10**5 and 1 <= r[1] <= 10**5 for r in rectangles)


def generate(rng):
    return ([[rng.randint(1, 6), rng.randint(1, 6)] for _ in range(rng.randint(1, 8))],)


MUTANTS = [
    {
        "id": "integer-ratio",
        "mutation": "wrong-operator",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def interchangeableRectangles(self, rectangles: List[List[int]]) -> int:
        count = {}
        res = 0

        for w, h in rectangles:
            count[w // h] = 1 + count.get(w // h, 0)

        for c in count.values():
            res += (c * (c - 1)) // 2

        return res
''',
    },
    {
        "id": "compares-every-pair",
        "mutation": "brute-force",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def interchangeableRectangles(self, rectangles: List[List[int]]) -> int:
        res = 0
        for i in range(len(rectangles)):
            for j in range(i + 1, len(rectangles)):
                if rectangles[i][0] * rectangles[j][1] == rectangles[j][0] * rectangles[i][1]:
                    res += 1
        return res
''',
    },
]

CLEAN_VARIANTS = []
