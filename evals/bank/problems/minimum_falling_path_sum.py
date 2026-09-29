from itertools import product

from evals.bank.controls import PRELUDE, external_code

NUMBER = 931
SLUG = "minimum-falling-path-sum"
TITLE = "Minimum Falling Path Sum"
DIFFICULTY = "Medium"
SPLIT = "test"
METHOD = "minFallingPathSum"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    (([[2, 1, 3], [6, 5, 4], [7, 8, 9]],), 13, "general"),
    (([[-19, 57], [-40, -5]],), -59, "general"),
    (([[1, 2, 3], [4, 5, 6], [7, 8, 9]],), 12, "general"),
    (([[3, 1], [1, 3]],), 2, "general"),
    (([[-1, -2], [-3, -4]],), -6, "general"),
    (([[5]],), 5, "edge"),
    (([[-100]],), -100, "edge"),
]

SCALE = ([[(r * 37 + c * 11) % 201 - 100 for c in range(100)] for r in range(100)],)
SPACE_SCALE = ([[(r * 37 + c * 11) % 201 - 100 for c in range(100)] for r in range(100)],)


def reference(matrix):
    n = len(matrix)
    best = None
    for start in range(n):
        for moves in product((-1, 0, 1), repeat=n - 1):
            col, total = start, matrix[0][start]
            for row, move in enumerate(moves, start=1):
                col += move
                if not 0 <= col < n:
                    break
                total += matrix[row][col]
            else:
                best = total if best is None else min(best, total)
    return best


def valid(matrix):
    # n == matrix.length == matrix[i].length, 1 <= n <= 100, -100 <= matrix[i][j] <= 100
    n = len(matrix)
    return 1 <= n <= 100 and all(len(row) == n and all(-100 <= x <= 100 for x in row) for row in matrix)


def generate(rng):
    n = rng.randint(1, 5)
    return ([[rng.randint(-9, 9) for _ in range(n)] for _ in range(n)],)


def is_edge(matrix):
    return len(matrix) == 1


MUTANTS = [
    {
        "id": "never-from-the-upper-right",
        "mutation": "off-by-one",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def minFallingPathSum(self, A: List[List[int]]) -> int:
        n = len(A)

        for i in range(1, n):
            for j in range(n):
                mn = math.inf
                for k in range(max(0, j - 1), min(n, j + 1)):
                    mn = min(mn, A[i - 1][k])
                A[i][j] += mn

        return min(A[-1])
''',
    },
    {
        "id": "best-starts-at-zero",
        "mutation": "wrong-init",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def minFallingPathSum(self, matrix: List[List[int]]) -> int:
        n = len(matrix)
        prev = matrix[0][:]
        for i in range(1, n):
            cur = [0] * n
            for j in range(n):
                cur[j] = matrix[i][j] + min(prev[max(0, j - 1):j + 2])
            prev = cur
        best = 0
        for value in prev:
            best = min(best, value)
        return best
''',
    },
    {
        "id": "answer-read-from-the-last-row-built",
        "mutation": "missing-guard",
        "intended": "edge-case",
        "code": PRELUDE + '''\
class Solution:
    def minFallingPathSum(self, matrix: List[List[int]]) -> int:
        n = len(matrix)
        prev = matrix[0]
        for i in range(1, n):
            cur = [matrix[i][j] + min(prev[max(0, j - 1):j + 2]) for j in range(n)]
            prev = cur
        return min(cur)
''',
    },
    {
        "id": "recursion-without-memo",
        "mutation": "naive-recursion",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def minFallingPathSum(self, matrix: List[List[int]]) -> int:
        n = len(matrix)

        def path(i, k):
            if k < 0 or k >= n:
                return float("inf")
            if i == n - 1:
                return matrix[i][k]
            return matrix[i][k] + min(path(i + 1, k - 1), path(i + 1, k), path(i + 1, k + 1))

        return min(path(0, k) for k in range(n))
''',
    },
]

CLEAN_VARIANTS = []
