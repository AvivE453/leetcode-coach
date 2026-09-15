from evals.bank.controls import PRELUDE, external_code

NUMBER = 329
SLUG = "longest-increasing-path-in-a-matrix"
TITLE = "Longest Increasing Path in a Matrix"
DIFFICULTY = "Hard"
SPLIT = "dev"
METHOD = "longestIncreasingPath"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    (([[9, 9, 4], [6, 6, 8], [2, 1, 1]],), 4, "general"),
    (([[3, 4, 5], [3, 2, 6], [2, 2, 1]],), 4, "general"),
    (([[1, 2]],), 2, "general"),
    (([[7, 7], [7, 7]],), 1, "general"),
    (([[1]],), 1, "edge"),
]

SCALE = ([[r + c for c in range(10)] for r in range(10)],)
SPACE_SCALE = ([[r * 200 + c for c in range(200)] for r in range(200)],)


def reference(matrix):
    rows, cols = len(matrix), len(matrix[0])

    def longest(r, c):
        return 1 + max((longest(nr, nc) for nr, nc in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1))
                        if 0 <= nr < rows and 0 <= nc < cols and matrix[nr][nc] > matrix[r][c]), default=0)

    return max(longest(r, c) for r in range(rows) for c in range(cols))


def generate(rng):
    # constraints: 1 <= m, n <= 200, 0 <= matrix[i][j] <= 2^31 - 1
    rows, cols = rng.randint(1, 3), rng.randint(1, 3)
    return ([[rng.randint(0, 5) for _ in range(cols)] for _ in range(rows)],)


MUTANTS = [
    {
        "id": "equal-neighbours-continue-the-path",
        "mutation": "wrong-operator",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def longestIncreasingPath(self, matrix: List[List[int]]) -> int:
        ROWS, COLS = len(matrix), len(matrix[0])
        dp = {}  # (r, c) -> LIP

        def dfs(r, c, prevVal):
            if r < 0 or r == ROWS or c < 0 or c == COLS or matrix[r][c] < prevVal:
                return 0
            if (r, c) in dp:
                return dp[(r, c)]

            res = 1
            res = max(res, 1 + dfs(r + 1, c, matrix[r][c]))
            res = max(res, 1 + dfs(r - 1, c, matrix[r][c]))
            res = max(res, 1 + dfs(r, c + 1, matrix[r][c]))
            res = max(res, 1 + dfs(r, c - 1, matrix[r][c]))
            dp[(r, c)] = res
            return res

        for r in range(ROWS):
            for c in range(COLS):
                dfs(r, c, -1)
        return max(dp.values())
''',
    },
    {
        "id": "a-step-adds-no-length",
        "mutation": "off-by-one",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def longestIncreasingPath(self, matrix: List[List[int]]) -> int:
        ROWS, COLS = len(matrix), len(matrix[0])
        dp = {}  # (r, c) -> LIP

        def dfs(r, c, prevVal):
            if r < 0 or r == ROWS or c < 0 or c == COLS or matrix[r][c] <= prevVal:
                return 0
            if (r, c) in dp:
                return dp[(r, c)]

            res = 1
            res = max(res, dfs(r + 1, c, matrix[r][c]))
            res = max(res, dfs(r - 1, c, matrix[r][c]))
            res = max(res, dfs(r, c + 1, matrix[r][c]))
            res = max(res, dfs(r, c - 1, matrix[r][c]))
            dp[(r, c)] = res
            return res

        for r in range(ROWS):
            for c in range(COLS):
                dfs(r, c, -1)
        return max(dp.values())
''',
    },
    {
        "id": "recursion-without-memo",
        "mutation": "naive-recursion",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def longestIncreasingPath(self, matrix: List[List[int]]) -> int:
        ROWS, COLS = len(matrix), len(matrix[0])

        def dfs(r, c, prevVal):
            if r < 0 or r == ROWS or c < 0 or c == COLS or matrix[r][c] <= prevVal:
                return 0

            res = 1
            res = max(res, 1 + dfs(r + 1, c, matrix[r][c]))
            res = max(res, 1 + dfs(r - 1, c, matrix[r][c]))
            res = max(res, 1 + dfs(r, c + 1, matrix[r][c]))
            res = max(res, 1 + dfs(r, c - 1, matrix[r][c]))
            return res

        return max(dfs(r, c, -1) for r in range(ROWS) for c in range(COLS))
''',
    },
]

CLEAN_VARIANTS = []
