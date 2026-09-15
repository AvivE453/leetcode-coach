NUMBER = 200
SLUG = "number-of-islands"
TITLE = "Number of Islands"
DIFFICULTY = "Medium"
SPLIT = "test"
METHOD = "numIslands"

# NeetCode's file does not parse (an over-indented BFS class), so it was rejected and this
# one is authored: in the test split it is the timing reference for the mutants, not a control.
CANONICAL = '''\
from collections import deque


class Solution:
    def numIslands(self, grid):
        rows, cols = len(grid), len(grid[0])
        seen = set()
        islands = 0
        for r in range(rows):
            for c in range(cols):
                if grid[r][c] == "1" and (r, c) not in seen:
                    islands += 1
                    seen.add((r, c))
                    queue = deque([(r, c)])
                    while queue:
                        row, col = queue.popleft()
                        for nr, nc in ((row + 1, col), (row - 1, col), (row, col + 1), (row, col - 1)):
                            if 0 <= nr < rows and 0 <= nc < cols and grid[nr][nc] == "1" and (nr, nc) not in seen:
                                seen.add((nr, nc))
                                queue.append((nr, nc))
        return islands
'''

TESTS = [
    (([["1", "1", "1", "1", "0"], ["1", "1", "0", "1", "0"], ["1", "1", "0", "0", "0"], ["0", "0", "0", "0", "0"]],),
     1, "general"),
    (([["1", "1", "0", "0", "0"], ["1", "1", "0", "0", "0"], ["0", "0", "1", "0", "0"], ["0", "0", "0", "1", "1"]],),
     3, "general"),
    (([["1", "0"], ["0", "1"]],), 2, "general"),
    (([["1", "0", "1"], ["1", "1", "1"]],), 1, "general"),
    (([["0"]],), 0, "edge"),
    (([["1"]],), 1, "edge"),
    (([["1", "0", "1"]],), 2, "edge"),
]

SCALE = ([["1"] * 30 for _ in range(30)],)
# Islands of four cells, so a recursive solution never recurses deep on the largest grid.
SPACE_SCALE = ([["0" if r % 3 == 2 or c % 3 == 2 else "1" for c in range(300)] for r in range(300)],)


def reference(grid):
    rows, cols = len(grid), len(grid[0])
    parent = {(r, c): (r, c) for r in range(rows) for c in range(cols) if grid[r][c] == "1"}

    def find(cell):
        while parent[cell] != cell:
            cell = parent[cell]
        return cell

    for r, c in list(parent):
        for nr, nc in ((r + 1, c), (r, c + 1)):
            if (nr, nc) in parent:
                parent[find((r, c))] = find((nr, nc))
    return len({find(cell) for cell in parent})


def generate(rng):
    # constraints: 1 <= m, n <= 300, grid[i][j] is "0" or "1"
    rows, cols = rng.randint(1, 5), rng.randint(1, 5)
    return ([[rng.choice("01") for _ in range(cols)] for _ in range(rows)],)


def is_edge(grid):
    return len(grid) == 1


MUTANTS = [
    {
        "id": "diagonals-connect",
        "mutation": "wrong-operator",
        "intended": "bug",
        "code": '''\
from collections import deque


class Solution:
    def numIslands(self, grid):
        rows, cols = len(grid), len(grid[0])
        seen = set()
        islands = 0
        for r in range(rows):
            for c in range(cols):
                if grid[r][c] == "1" and (r, c) not in seen:
                    islands += 1
                    seen.add((r, c))
                    queue = deque([(r, c)])
                    while queue:
                        row, col = queue.popleft()
                        for dr in (-1, 0, 1):
                            for dc in (-1, 0, 1):
                                nr, nc = row + dr, col + dc
                                if 0 <= nr < rows and 0 <= nc < cols and grid[nr][nc] == "1" and (nr, nc) not in seen:
                                    seen.add((nr, nc))
                                    queue.append((nr, nc))
        return islands
''',
    },
    {
        "id": "width-read-from-second-row",
        "mutation": "off-by-one",
        "intended": "edge-case",
        "code": '''\
from collections import deque


class Solution:
    def numIslands(self, grid):
        rows, cols = len(grid), len(grid[1])
        seen = set()
        islands = 0
        for r in range(rows):
            for c in range(cols):
                if grid[r][c] == "1" and (r, c) not in seen:
                    islands += 1
                    seen.add((r, c))
                    queue = deque([(r, c)])
                    while queue:
                        row, col = queue.popleft()
                        for nr, nc in ((row + 1, col), (row - 1, col), (row, col + 1), (row, col - 1)):
                            if 0 <= nr < rows and 0 <= nc < cols and grid[nr][nc] == "1" and (nr, nc) not in seen:
                                seen.add((nr, nc))
                                queue.append((nr, nc))
        return islands
''',
    },
    {
        "id": "explores-from-every-cell",
        "mutation": "brute-force",
        "intended": "complexity",
        "code": '''\
from collections import deque


class Solution:
    def numIslands(self, grid):
        rows, cols = len(grid), len(grid[0])
        islands = 0
        for r in range(rows):
            for c in range(cols):
                if grid[r][c] != "1":
                    continue
                seen = {(r, c)}
                queue = deque([(r, c)])
                while queue:
                    row, col = queue.popleft()
                    for nr, nc in ((row + 1, col), (row - 1, col), (row, col + 1), (row, col - 1)):
                        if 0 <= nr < rows and 0 <= nc < cols and grid[nr][nc] == "1" and (nr, nc) not in seen:
                            seen.add((nr, nc))
                            queue.append((nr, nc))
                if min(seen) == (r, c):
                    islands += 1
        return islands
''',
    },
]

CLEAN_VARIANTS = []
