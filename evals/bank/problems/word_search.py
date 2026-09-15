from evals.bank.controls import PRELUDE, external_code

NUMBER = 79
SLUG = "word-search"
TITLE = "Word Search"
DIFFICULTY = "Medium"
SPLIT = "test"
METHOD = "exist"

CANONICAL = external_code("neetcode", NUMBER)

BOARD = [["A", "B", "C", "E"], ["S", "F", "C", "S"], ["A", "D", "E", "E"]]

TESTS = [
    ((BOARD, "ABCCED"), True, "general"),
    ((BOARD, "SEE"), True, "general"),
    ((BOARD, "ABCB"), False, "general"),
    (([["a", "b"], ["c", "d"]], "abdc"), True, "general"),
    (([["a", "b"], ["c", "d"]], "abcd"), False, "general"),
    (([["a", "b"]], "aa"), False, "general"),
    (([["a"]], "a"), True, "edge"),
    (([["a"]], "b"), False, "edge"),
]

# An ordinary board, not a worst case: NeetCode reverses the word when that prunes the
# search, and a board built to reward that one heuristic would call every sound solution slow.
SCALE = (BOARD, "ABCCED")
SPACE_SCALE = (BOARD, "ABCCED")


def reference(board, word):
    rows, cols = len(board), len(board[0])

    def walk(r, c, i, used):
        if board[r][c] != word[i]:
            return False
        if i == len(word) - 1:
            return True
        used = used | {(r, c)}
        return any(0 <= nr < rows and 0 <= nc < cols and (nr, nc) not in used and walk(nr, nc, i + 1, used)
                   for nr, nc in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)))

    return any(walk(r, c, 0, frozenset()) for r in range(rows) for c in range(cols))


def generate(rng):
    # constraints: 1 <= m, n <= 6, 1 <= word.length <= 15, English letters
    rows, cols = rng.randint(1, 4), rng.randint(1, 4)
    board = [[rng.choice("ab") for _ in range(cols)] for _ in range(rows)]
    if rng.random() < 0.5:
        r, c = rng.randrange(rows), rng.randrange(cols)
        word = board[r][c]
        for _ in range(rng.randint(0, 4)):
            r, c = rng.choice([(r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)])
            if not (0 <= r < rows and 0 <= c < cols):
                break
            word += board[r][c]
    else:
        word = "".join(rng.choice("ab") for _ in range(rng.randint(1, 5)))
    return (board, word)


MUTANTS = [
    {
        "id": "cells-can-be-reused",
        "mutation": "missing-guard",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def exist(self, board: List[List[str]], word: str) -> bool:
        ROWS, COLS = len(board), len(board[0])
        path = set()

        def dfs(r, c, i):
            if i == len(word):
                return True
            if (
                min(r, c) < 0
                or r >= ROWS
                or c >= COLS
                or word[i] != board[r][c]
            ):
                return False
            path.add((r, c))
            res = (
                dfs(r + 1, c, i + 1)
                or dfs(r - 1, c, i + 1)
                or dfs(r, c + 1, i + 1)
                or dfs(r, c - 1, i + 1)
            )
            path.remove((r, c))
            return res

        # To prevent TLE,reverse the word if frequency of the first letter is more than the last letter's
        count = sum(map(Counter, board), Counter())
        if count[word[0]] > count[word[-1]]:
            word = word[::-1]

        for r in range(ROWS):
            for c in range(COLS):
                if dfs(r, c, 0):
                    return True
        return False
''',
    },
    {
        "id": "last-letter-never-checked",
        "mutation": "off-by-one",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def exist(self, board: List[List[str]], word: str) -> bool:
        ROWS, COLS = len(board), len(board[0])
        path = set()

        def dfs(r, c, i):
            if i == len(word) - 1:
                return True
            if (
                min(r, c) < 0
                or r >= ROWS
                or c >= COLS
                or word[i] != board[r][c]
                or (r, c) in path
            ):
                return False
            path.add((r, c))
            res = (
                dfs(r + 1, c, i + 1)
                or dfs(r - 1, c, i + 1)
                or dfs(r, c + 1, i + 1)
                or dfs(r, c - 1, i + 1)
            )
            path.remove((r, c))
            return res

        # To prevent TLE,reverse the word if frequency of the first letter is more than the last letter's
        count = sum(map(Counter, board), Counter())
        if count[word[0]] > count[word[-1]]:
            word = word[::-1]

        for r in range(ROWS):
            for c in range(COLS):
                if dfs(r, c, 0):
                    return True
        return False
''',
    },
]

CLEAN_VARIANTS = []
