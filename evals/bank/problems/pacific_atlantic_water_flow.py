from evals.bank.controls import PRELUDE, external_code

NUMBER = 417
SLUG = "pacific-atlantic-water-flow"
TITLE = "Pacific Atlantic Water Flow"
DIFFICULTY = "Medium"
SPLIT = "test"
METHOD = "pacificAtlantic"

CANONICAL = external_code("neetcode", NUMBER)

ISLAND = [[1, 2, 2, 3, 5], [3, 2, 3, 4, 4], [2, 4, 5, 3, 1], [6, 7, 1, 4, 5], [5, 1, 1, 2, 4]]

TESTS = [
    ((ISLAND,), [[0, 4], [1, 3], [1, 4], [2, 2], [3, 0], [3, 1], [4, 0]], "general"),
    (([[1, 1], [1, 1]],), [[0, 0], [0, 1], [1, 0], [1, 1]], "general"),
    (([[3, 3, 3], [3, 1, 3], [0, 2, 4]],), [[0, 0], [0, 1], [0, 2], [1, 0], [1, 2], [2, 0], [2, 1], [2, 2]], "general"),
    (([[1]],), [[0, 0]], "edge"),
]


def pyramid(size):
    return [[min(r, c, size - 1 - r, size - 1 - c) for c in range(size)] for r in range(size)]


SCALE = (pyramid(25),)
# Not the 200 x 200 the constraints allow: under the memory tracer the recursive canonical
# outlasts the oracle's timeout there, and 80 x 80 still separates O(mn) from O((mn)^2).
SPACE_SCALE = (pyramid(80),)


def normalize(cells):
    """LeetCode accepts the cells in any order."""
    return sorted(list(cell) for cell in cells)


def reference(heights):
    rows, cols = len(heights), len(heights[0])
    result = []
    for r in range(rows):
        for c in range(cols):
            seen = {(r, c)}
            stack = [(r, c)]
            pacific = atlantic = False
            while stack:
                row, col = stack.pop()
                pacific |= row == 0 or col == 0
                atlantic |= row == rows - 1 or col == cols - 1
                for nr, nc in ((row + 1, col), (row - 1, col), (row, col + 1), (row, col - 1)):
                    if (0 <= nr < rows and 0 <= nc < cols and (nr, nc) not in seen
                            and heights[nr][nc] <= heights[row][col]):
                        seen.add((nr, nc))
                        stack.append((nr, nc))
            if pacific and atlantic:
                result.append([r, c])
    return result


def generate(rng):
    # constraints: 1 <= m, n <= 200, 0 <= heights[r][c] <= 10^5
    rows, cols = rng.randint(1, 4), rng.randint(1, 4)
    return ([[rng.randint(0, 4) for _ in range(cols)] for _ in range(rows)],)


MUTANTS = [
    {
        "id": "water-needs-a-strict-drop",
        "mutation": "wrong-operator",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def pacificAtlantic(self, heights: List[List[int]]) -> List[List[int]]:
        ROWS, COLS = len(heights), len(heights[0])
        pac, atl = set(), set()

        def dfs(r, c, visit, prevHeight):
            if (
                (r, c) in visit
                or r < 0
                or c < 0
                or r == ROWS
                or c == COLS
                or heights[r][c] <= prevHeight
            ):
                return
            visit.add((r, c))
            dfs(r + 1, c, visit, heights[r][c])
            dfs(r - 1, c, visit, heights[r][c])
            dfs(r, c + 1, visit, heights[r][c])
            dfs(r, c - 1, visit, heights[r][c])

        for c in range(COLS):
            dfs(0, c, pac, heights[0][c])
            dfs(ROWS - 1, c, atl, heights[ROWS - 1][c])

        for r in range(ROWS):
            dfs(r, 0, pac, heights[r][0])
            dfs(r, COLS - 1, atl, heights[r][COLS - 1])

        res = []
        for r in range(ROWS):
            for c in range(COLS):
                if (r, c) in pac and (r, c) in atl:
                    res.append([r, c])
        return res
''',
    },
    {
        "id": "one-visited-set-for-both-oceans",
        "mutation": "weaker-structure",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def pacificAtlantic(self, heights: List[List[int]]) -> List[List[int]]:
        ROWS, COLS = len(heights), len(heights[0])
        pac = set()
        atl = pac

        def dfs(r, c, visit, prevHeight):
            if (
                (r, c) in visit
                or r < 0
                or c < 0
                or r == ROWS
                or c == COLS
                or heights[r][c] < prevHeight
            ):
                return
            visit.add((r, c))
            dfs(r + 1, c, visit, heights[r][c])
            dfs(r - 1, c, visit, heights[r][c])
            dfs(r, c + 1, visit, heights[r][c])
            dfs(r, c - 1, visit, heights[r][c])

        for c in range(COLS):
            dfs(0, c, pac, heights[0][c])
            dfs(ROWS - 1, c, atl, heights[ROWS - 1][c])

        for r in range(ROWS):
            dfs(r, 0, pac, heights[r][0])
            dfs(r, COLS - 1, atl, heights[r][COLS - 1])

        res = []
        for r in range(ROWS):
            for c in range(COLS):
                if (r, c) in pac and (r, c) in atl:
                    res.append([r, c])
        return res
''',
    },
    {
        "id": "search-from-every-cell",
        "mutation": "brute-force",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def pacificAtlantic(self, heights: List[List[int]]) -> List[List[int]]:
        ROWS, COLS = len(heights), len(heights[0])
        res = []
        for r in range(ROWS):
            for c in range(COLS):
                seen = {(r, c)}
                stack = [(r, c)]
                pacific = atlantic = False
                while stack:
                    row, col = stack.pop()
                    pacific = pacific or row == 0 or col == 0
                    atlantic = atlantic or row == ROWS - 1 or col == COLS - 1
                    for nr, nc in ((row + 1, col), (row - 1, col), (row, col + 1), (row, col - 1)):
                        if (0 <= nr < ROWS and 0 <= nc < COLS and (nr, nc) not in seen
                                and heights[nr][nc] <= heights[row][col]):
                            seen.add((nr, nc))
                            stack.append((nr, nc))
                if pacific and atlantic:
                    res.append([r, c])
        return res
''',
    },
]

CLEAN_VARIANTS = []
