from itertools import permutations

from evals.bank.controls import PRELUDE, external_code

NUMBER = 51
SLUG = "n-queens"
TITLE = "N-Queens"
DIFFICULTY = "Hard"
SPLIT = "dev"
METHOD = "solveNQueens"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    ((4,), [[".Q..", "...Q", "Q...", "..Q."], ["..Q.", "Q...", "...Q", ".Q.."]], "general"),
    ((2,), [], "general"),
    ((3,), [], "general"),
    ((1,), [["Q"]], "edge"),
]

SCALE = (8,)
SPACE_SCALE = (9,)
DIFFERENTIAL_CASES = 50


def normalize(boards):
    """LeetCode accepts the boards in any order."""
    return sorted(boards)


def reference(n):
    boards = []
    for cols in permutations(range(n)):
        if len({r + c for r, c in enumerate(cols)}) == n and len({r - c for r, c in enumerate(cols)}) == n:
            boards.append(["." * c + "Q" + "." * (n - c - 1) for c in cols])
    return boards


def generate(rng):
    # constraints: 1 <= n <= 9
    return (rng.randint(1, 7),)


MUTANTS = [
    {
        "id": "one-diagonal-checked",
        "mutation": "missing-guard",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def solveNQueens(self, n: int) -> List[List[str]]:
        col = set()
        posDiag = set()  # (r + c)

        res = []
        board = [["."] * n for i in range(n)]

        def backtrack(r):
            if r == n:
                copy = ["".join(row) for row in board]
                res.append(copy)
                return

            for c in range(n):
                if c in col or (r + c) in posDiag:
                    continue

                col.add(c)
                posDiag.add(r + c)
                board[r][c] = "Q"

                backtrack(r + 1)

                col.remove(c)
                posDiag.remove(r + c)
                board[r][c] = "."

        backtrack(0)
        return res
''',
    },
    {
        "id": "stores-the-board-not-a-copy",
        "mutation": "weaker-structure",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def solveNQueens(self, n: int) -> List[List[str]]:
        col = set()
        posDiag = set()  # (r + c)
        negDiag = set()  # (r - c)

        res = []
        board = [["."] * n for i in range(n)]

        def backtrack(r):
            if r == n:
                res.append(board)
                return

            for c in range(n):
                if c in col or (r + c) in posDiag or (r - c) in negDiag:
                    continue

                col.add(c)
                posDiag.add(r + c)
                negDiag.add(r - c)
                board[r][c] = "Q"

                backtrack(r + 1)

                col.remove(c)
                posDiag.remove(r + c)
                negDiag.remove(r - c)
                board[r][c] = "."

        backtrack(0)
        return res
''',
    },
    {
        "id": "every-column-permutation",
        "mutation": "brute-force",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def solveNQueens(self, n: int) -> List[List[str]]:
        res = []
        for cols in itertools.permutations(range(n)):
            if len({r + c for r, c in enumerate(cols)}) == n and len({r - c for r, c in enumerate(cols)}) == n:
                res.append(["." * c + "Q" + "." * (n - c - 1) for c in cols])
        return res
''',
    },
]

CLEAN_VARIANTS = []
