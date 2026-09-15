from evals.bank.controls import PRELUDE, external_code

NUMBER = 778
SLUG = "swim-in-rising-water"
TITLE = "Swim in Rising Water"
DIFFICULTY = "Hard"
SPLIT = "dev"
METHOD = "swimInWater"

CANONICAL = external_code("neetcode", NUMBER)

SPIRAL = [[0, 1, 2, 3, 4], [24, 23, 22, 21, 5], [12, 13, 14, 15, 16], [11, 17, 18, 19, 20], [10, 9, 8, 7, 6]]

TESTS = [
    (([[0, 2], [1, 3]],), 3, "general"),
    ((SPIRAL,), 16, "general"),
    (([[3, 2], [0, 1]],), 3, "general"),
    (([[0]],), 0, "edge"),
]

SCALE = ([[r * 30 + c for c in range(30)] for r in range(30)],)
SPACE_SCALE = ([[r * 50 + c for c in range(50)] for r in range(50)],)


def reference(grid):
    n = len(grid)
    for t in range(n * n):
        if grid[0][0] > t:
            continue
        seen = {(0, 0)}
        stack = [(0, 0)]
        while stack:
            r, c = stack.pop()
            if (r, c) == (n - 1, n - 1):
                return t
            for nr, nc in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)):
                if 0 <= nr < n and 0 <= nc < n and (nr, nc) not in seen and grid[nr][nc] <= t:
                    seen.add((nr, nc))
                    stack.append((nr, nc))


def generate(rng):
    # constraints: 1 <= n <= 50, grid holds each of 0 .. n^2 - 1 exactly once
    n = rng.randint(1, 4)
    values = list(range(n * n))
    rng.shuffle(values)
    return ([values[r * n: (r + 1) * n] for r in range(n)],)


MUTANTS = [
    {
        "id": "start-height-ignored",
        "mutation": "wrong-init",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def swimInWater(self, grid: List[List[int]]) -> int:
        N = len(grid)
        visit = set()
        minH = [[0, 0, 0]]  # (time/max-height, r, c)
        directions = [[0, 1], [0, -1], [1, 0], [-1, 0]]

        visit.add((0, 0))
        while minH:
            t, r, c = heapq.heappop(minH)
            if r == N - 1 and c == N - 1:
                return t
            for dr, dc in directions:
                neiR, neiC = r + dr, c + dc
                if (
                    neiR < 0
                    or neiC < 0
                    or neiR == N
                    or neiC == N
                    or (neiR, neiC) in visit
                ):
                    continue
                visit.add((neiR, neiC))
                heapq.heappush(minH, [max(t, grid[neiR][neiC]), neiR, neiC])
''',
    },
    {
        "id": "first-arrival-not-lowest",
        "mutation": "greedy-substitution",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def swimInWater(self, grid: List[List[int]]) -> int:
        N = len(grid)
        visit = set()
        minH = collections.deque([[grid[0][0], 0, 0]])  # (time/max-height, r, c)
        directions = [[0, 1], [0, -1], [1, 0], [-1, 0]]

        visit.add((0, 0))
        while minH:
            t, r, c = minH.popleft()
            if r == N - 1 and c == N - 1:
                return t
            for dr, dc in directions:
                neiR, neiC = r + dr, c + dc
                if (
                    neiR < 0
                    or neiC < 0
                    or neiR == N
                    or neiC == N
                    or (neiR, neiC) in visit
                ):
                    continue
                visit.add((neiR, neiC))
                minH.append([max(t, grid[neiR][neiC]), neiR, neiC])
''',
    },
    {
        "id": "try-every-water-level",
        "mutation": "brute-force",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def swimInWater(self, grid: List[List[int]]) -> int:
        N = len(grid)
        for t in range(N * N):
            if grid[0][0] > t:
                continue
            visit = {(0, 0)}
            stack = [(0, 0)]
            while stack:
                r, c = stack.pop()
                if r == N - 1 and c == N - 1:
                    return t
                for dr, dc in [[0, 1], [0, -1], [1, 0], [-1, 0]]:
                    neiR, neiC = r + dr, c + dc
                    if 0 <= neiR < N and 0 <= neiC < N and (neiR, neiC) not in visit and grid[neiR][neiC] <= t:
                        visit.add((neiR, neiC))
                        stack.append((neiR, neiC))
''',
    },
]

CLEAN_VARIANTS = []
