from evals.bank.controls import PRELUDE, external_code

NUMBER = 221
SLUG = "maximal-square"
TITLE = "Maximal Square"
DIFFICULTY = "Medium"
SPLIT = "test"
METHOD = "maximalSquare"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    (([["1", "0", "1", "0", "0"], ["1", "0", "1", "1", "1"], ["1", "1", "1", "1", "1"], ["1", "0", "0", "1", "0"]],),
     4, "general"),
    (([["0", "1"], ["1", "0"]],), 1, "general"),
    (([["1", "1", "1"], ["1", "1", "1"], ["1", "1", "1"]],), 9, "general"),
    (([["1", "1"], ["1", "1"], ["1", "0"]],), 4, "general"),
    (([["0", "0", "1"], ["0", "1", "1"], ["1", "1", "1"]],), 4, "general"),
    (([["0"]],), 0, "edge"),
    (([["1"]],), 1, "edge"),
    (([["1", "1", "1", "1"]],), 1, "edge"),
]

SCALE = ([["1"] * 40 for _ in range(40)],)
SPACE_SCALE = ([["1"] * 100 for _ in range(100)],)


def reference(matrix):
    rows, cols = len(matrix), len(matrix[0])
    best = 0
    for top in range(rows):
        for left in range(cols):
            size = 1
            while top + size <= rows and left + size <= cols and all(
                    matrix[r][c] == "1" for r in range(top, top + size) for c in range(left, left + size)):
                best = max(best, size)
                size += 1
    return best * best


def valid(matrix):
    # 1 <= m, n <= 300, every row n long, matrix[i][j] is '0' or '1'
    return (1 <= len(matrix) <= 300 and 1 <= len(matrix[0]) <= 300
            and all(len(row) == len(matrix[0]) and all(cell in ("0", "1") for cell in row) for row in matrix))


def generate(rng):
    rows, cols = rng.randint(1, 5), rng.randint(1, 5)
    return ([["1" if rng.random() < 0.7 else "0" for _ in range(cols)] for _ in range(rows)],)


MUTANTS = [
    {
        "id": "grows-from-the-largest-neighbour",
        "mutation": "wrong-operator",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def maximalSquare(self, matrix: List[List[str]]) -> int:
        ROWS, COLS = len(matrix), len(matrix[0])
        cache = {}

        def helper(r, c):
            if r >= ROWS or c >= COLS:
                return 0

            if (r, c) not in cache:
                down = helper(r + 1, c)
                right = helper(r, c + 1)
                diag = helper(r + 1, c + 1)

                cache[(r, c)] = 0
                if matrix[r][c] == "1":
                    cache[(r, c)] = 1 + max(down, right, diag)
            return cache[(r, c)]

        helper(0, 0)
        return max(cache.values()) ** 2
''',
    },
    {
        "id": "border-never-counted",
        "mutation": "off-by-one",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def maximalSquare(self, matrix: List[List[str]]) -> int:
        m = len(matrix)
        n = len(matrix[0])
        dp = [[1 if cell == '1' else 0 for cell in row] for row in matrix]
        maxLength = 0

        for i in range(1, m):
            for j in range(1, n):
                if matrix[i][j] == '1':
                    dp[i][j] = min(dp[i - 1][j - 1], dp[i - 1][j], dp[i][j - 1]) + 1
                maxLength = max(maxLength, dp[i][j])

        return maxLength * maxLength
''',
    },
    {
        "id": "checks-every-square",
        "mutation": "brute-force",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def maximalSquare(self, matrix: List[List[str]]) -> int:
        m, n = len(matrix), len(matrix[0])
        best = 0
        for i in range(m):
            for j in range(n):
                size = 1
                while i + size <= m and j + size <= n and all(
                        matrix[r][c] == '1' for r in range(i, i + size) for c in range(j, j + size)):
                    best = max(best, size)
                    size += 1
        return best * best
''',
    },
]

CLEAN_VARIANTS = []
