from itertools import permutations

from evals.bank.controls import PRELUDE, external_code

NUMBER = 52
SLUG = "n-queens-ii"
TITLE = "N-Queens II"
DIFFICULTY = "Hard"
SPLIT = "test"
METHOD = "totalNQueens"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    ((4,), 2, "general"),
    ((5,), 10, "general"),
    ((6,), 4, "general"),
    ((8,), 92, "general"),
    ((1,), 1, "edge"),
    ((2,), 0, "edge"),
    ((3,), 0, "edge"),
]

# n is at most 9, so no search is slower in a way that matters, and the problem has no
# complexity mutant.
SCALE = (9,)
SPACE_SCALE = (9,)
# Seven boards to check, each a brute force over n! placements: a few dozen draws cover them.
DIFFERENTIAL_CASES = 50


def reference(n):
    return sum(len({r + c for r, c in enumerate(cols)}) == n and len({r - c for r, c in enumerate(cols)}) == n
               for cols in permutations(range(n)))


def valid(n):
    # 1 <= n <= 9
    return 1 <= n <= 9


def generate(rng):
    return (rng.randint(1, 7),)


MUTANTS = [
    {
        "id": "one-diagonal-unchecked",
        "mutation": "missing-guard",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def totalNQueens(self, n: int) -> int:
        answer = 0

        cols = set()
        posdiag = set()

        def backtrack(i):
            if i == n:
                nonlocal answer
                answer += 1
                return

            for j in range(n):
                if j in cols or (i + j) in posdiag:
                    continue

                cols.add(j)
                posdiag.add(i + j)

                backtrack(i + 1)

                cols.remove(j)
                posdiag.remove(i + j)

        backtrack(0)
        return answer
''',
    },
    {
        "id": "diagonals-keyed-by-distance",
        "mutation": "wrong-operator",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def totalNQueens(self, n: int) -> int:
        answer = 0

        cols = set()
        posdiag = set()
        negdiag = set()

        def backtrack(i):
            if i == n:
                nonlocal answer
                answer += 1
                return

            for j in range(n):
                if j in cols or (i + j) in posdiag or abs(i - j) in negdiag:
                    continue

                cols.add(j)
                posdiag.add(i + j)
                negdiag.add(abs(i - j))

                backtrack(i + 1)

                cols.remove(j)
                posdiag.remove(i + j)
                negdiag.remove(abs(i - j))

        backtrack(0)
        return answer
''',
    },
]

CLEAN_VARIANTS = []
