import math

from evals.bank.controls import PRELUDE, external_code

NUMBER = 62
SLUG = "unique-paths"
TITLE = "Unique Paths"
DIFFICULTY = "Medium"
SPLIT = "dev"
METHOD = "uniquePaths"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    ((3, 7), 28, "general"),
    ((3, 2), 3, "general"),
    ((7, 3), 28, "general"),
    ((1, 1), 1, "edge"),
    ((1, 5), 1, "edge"),
]

SCALE = (12, 12)
SPACE_SCALE = (17, 17)


def reference(m, n):
    return math.comb(m + n - 2, m - 1)


def generate(rng):
    # constraints: 1 <= m, n <= 100, and the answer is at most 2 * 10^9
    return (rng.randint(1, 10), rng.randint(1, 10))


MUTANTS = [
    {
        "id": "reads-the-row-being-written",
        "mutation": "weaker-structure",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def uniquePaths(self, m: int, n: int) -> int:
        row = [1] * n

        for i in range(m - 1):
            newRow = [1] * n
            for j in range(n - 2, -1, -1):
                newRow[j] = newRow[j + 1] + newRow[j]
            row = newRow
        return row[0]
''',
    },
    {
        "id": "one-row-short",
        "mutation": "off-by-one",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def uniquePaths(self, m: int, n: int) -> int:
        row = [1] * n

        for i in range(m - 2):
            newRow = [1] * n
            for j in range(n - 2, -1, -1):
                newRow[j] = newRow[j + 1] + row[j]
            row = newRow
        return row[0]
''',
    },
    {
        "id": "recursion-without-memo",
        "mutation": "naive-recursion",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def uniquePaths(self, m: int, n: int) -> int:
        def paths(r, c):
            if r == m - 1 or c == n - 1:
                return 1
            return paths(r + 1, c) + paths(r, c + 1)

        return paths(0, 0)
''',
    },
]

CLEAN_VARIANTS = []
