from evals.bank.controls import PRELUDE, external_code

NUMBER = 54
SLUG = "spiral-matrix"
TITLE = "Spiral Matrix"
DIFFICULTY = "Medium"
SPLIT = "test"
METHOD = "spiralOrder"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    (([[1, 2, 3], [4, 5, 6], [7, 8, 9]],), [1, 2, 3, 6, 9, 8, 7, 4, 5], "general"),
    (([[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12]],), [1, 2, 3, 4, 8, 12, 11, 10, 9, 5, 6, 7], "general"),
    (([[1, 2], [3, 4], [5, 6]],), [1, 2, 4, 6, 5, 3], "general"),
    (([[1], [2], [3]],), [1, 2, 3], "edge"),
    (([[1, 2, 3]],), [1, 2, 3], "edge"),
    (([[7]],), [7], "edge"),
]

SCALE = ([[r * 10 + c for c in range(10)] for r in range(10)],)
SPACE_SCALE = ([[r * 10 + c for c in range(10)] for r in range(10)],)


def reference(matrix):
    rows, cols = len(matrix), len(matrix[0])
    moves = [(0, 1), (1, 0), (0, -1), (-1, 0)]
    seen = set()
    order = []
    r = c = d = 0
    for _ in range(rows * cols):
        order.append(matrix[r][c])
        seen.add((r, c))
        dr, dc = moves[d]
        if not (0 <= r + dr < rows and 0 <= c + dc < cols) or (r + dr, c + dc) in seen:
            d = (d + 1) % 4
            dr, dc = moves[d]
        r, c = r + dr, c + dc
    return order


def generate(rng):
    # constraints: 1 <= m, n <= 10, -100 <= matrix[i][j] <= 100
    rows, cols = rng.randint(1, 5), rng.randint(1, 5)
    return ([[rng.randint(-9, 9) for _ in range(cols)] for _ in range(rows)],)


MUTANTS = [
    {
        "id": "no-break-between-halves",
        "mutation": "missing-guard",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def spiralOrder(self, matrix: List[List[int]]) -> List[int]:
        res = []
        left, right = 0, len(matrix[0])
        top, bottom = 0, len(matrix)

        while left < right and top < bottom:
            # get every i in the top row
            for i in range(left, right):
                res.append(matrix[top][i])
            top += 1
            # get every i in the right col
            for i in range(top, bottom):
                res.append(matrix[i][right - 1])
            right -= 1
            # get every i in the bottom row
            for i in range(right - 1, left - 1, -1):
                res.append(matrix[bottom - 1][i])
            bottom -= 1
            # get every i in the left col
            for i in range(bottom - 1, top - 1, -1):
                res.append(matrix[i][left])
            left += 1

        return res
''',
    },
    {
        "id": "bottom-row-stops-early",
        "mutation": "off-by-one",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def spiralOrder(self, matrix: List[List[int]]) -> List[int]:
        res = []
        left, right = 0, len(matrix[0])
        top, bottom = 0, len(matrix)

        while left < right and top < bottom:
            # get every i in the top row
            for i in range(left, right):
                res.append(matrix[top][i])
            top += 1
            # get every i in the right col
            for i in range(top, bottom):
                res.append(matrix[i][right - 1])
            right -= 1
            if not (left < right and top < bottom):
                break
            # get every i in the bottom row
            for i in range(right - 1, left, -1):
                res.append(matrix[bottom - 1][i])
            bottom -= 1
            # get every i in the left col
            for i in range(bottom - 1, top - 1, -1):
                res.append(matrix[i][left])
            left += 1

        return res
''',
    },
]

CLEAN_VARIANTS = []
