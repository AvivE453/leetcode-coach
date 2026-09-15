from evals.bank.controls import PRELUDE, external_code

NUMBER = 212
SLUG = "word-search-ii"
TITLE = "Word Search II"
DIFFICULTY = "Hard"
SPLIT = "test"
METHOD = "findWords"

CANONICAL = external_code("neetcode", NUMBER)

BOARD = [["o", "a", "a", "n"], ["e", "t", "a", "e"], ["i", "h", "k", "r"], ["i", "f", "l", "v"]]
SQUARE = [["a", "b"], ["c", "d"]]

TESTS = [
    ((BOARD, ["oath", "pea", "eat", "rain"]), ["eat", "oath"], "general"),
    ((SQUARE, ["ab", "cb", "ad", "bd", "ac", "ca", "da", "bc", "db", "adcb", "dabc", "abb", "acb"]),
     ["ab", "ac", "bd", "ca", "db"], "general"),
    (([["a", "a"]], ["aaa"]), [], "general"),
    (([["a", "b", "c"]], ["ab", "abc"]), ["ab", "abc"], "general"),
    (([["a"]], ["a"]), ["a"], "edge"),
    (([["a"]], ["b"]), [], "edge"),
]

SCALE = ([["a"] * 4 for _ in range(4)], ["aaaaa" + ch for ch in "bcdefghijklmnopqrstuvwxyz"])
SPACE_SCALE = ([[chr(97 + (r * 12 + c) % 5) for c in range(12)] for r in range(12)],
               ["".join(chr(97 + (i // 5**j) % 5) for j in range(5)) for i in range(2000)])


def normalize(words):
    """LeetCode accepts the found words in any order."""
    return sorted(words)


def reference(board, words):
    rows, cols = len(board), len(board[0])

    def walk(r, c, word, i, used):
        if board[r][c] != word[i]:
            return False
        if i == len(word) - 1:
            return True
        used = used | {(r, c)}
        return any(0 <= nr < rows and 0 <= nc < cols and (nr, nc) not in used and walk(nr, nc, word, i + 1, used)
                   for nr, nc in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)))

    return [word for word in words
            if any(walk(r, c, word, 0, frozenset()) for r in range(rows) for c in range(cols))]


def generate(rng):
    # constraints: 1 <= m, n <= 12, 1 <= words.length <= 3 * 10^4, 1 <= words[i].length <= 10,
    # lowercase letters, and the words are unique
    rows, cols = rng.randint(1, 3), rng.randint(1, 3)
    board = [[rng.choice("ab") for _ in range(cols)] for _ in range(rows)]
    words = {"".join(rng.choice("abc") for _ in range(rng.randint(1, 4))) for _ in range(rng.randint(1, 5))}
    return (board, sorted(words))


MUTANTS = [
    {
        "id": "cells-can-be-reused",
        "mutation": "missing-guard",
        "intended": "bug",
        "code": PRELUDE + '''\
class TrieNode:
    def __init__(self):
        self.children = {}
        self.isWord = False
        self.refs = 0

    def addWord(self, word):
        cur = self
        cur.refs += 1
        for c in word:
            if c not in cur.children:
                cur.children[c] = TrieNode()
            cur = cur.children[c]
            cur.refs += 1
        cur.isWord = True

    def removeWord(self, word):
        cur = self
        cur.refs -= 1
        for c in word:
            if c in cur.children:
                cur = cur.children[c]
                cur.refs -= 1


class Solution:
    def findWords(self, board: List[List[str]], words: List[str]) -> List[str]:
        root = TrieNode()
        for w in words:
            root.addWord(w)

        ROWS, COLS = len(board), len(board[0])
        res = set()

        def dfs(r, c, node, word):
            if (
                r not in range(ROWS)
                or c not in range(COLS)
                or board[r][c] not in node.children
                or node.children[board[r][c]].refs < 1
            ):
                return

            node = node.children[board[r][c]]
            word += board[r][c]
            if node.isWord:
                node.isWord = False
                res.add(word)
                root.removeWord(word)

            dfs(r + 1, c, node, word)
            dfs(r - 1, c, node, word)
            dfs(r, c + 1, node, word)
            dfs(r, c - 1, node, word)

        for r in range(ROWS):
            for c in range(COLS):
                dfs(r, c, root, "")

        return list(res)
''',
    },
    {
        "id": "stops-at-the-first-word-on-a-path",
        "mutation": "missing-precondition",
        "intended": "bug",
        "code": PRELUDE + '''\
class TrieNode:
    def __init__(self):
        self.children = {}
        self.isWord = False
        self.refs = 0

    def addWord(self, word):
        cur = self
        cur.refs += 1
        for c in word:
            if c not in cur.children:
                cur.children[c] = TrieNode()
            cur = cur.children[c]
            cur.refs += 1
        cur.isWord = True

    def removeWord(self, word):
        cur = self
        cur.refs -= 1
        for c in word:
            if c in cur.children:
                cur = cur.children[c]
                cur.refs -= 1


class Solution:
    def findWords(self, board: List[List[str]], words: List[str]) -> List[str]:
        root = TrieNode()
        for w in words:
            root.addWord(w)

        ROWS, COLS = len(board), len(board[0])
        res, visit = set(), set()

        def dfs(r, c, node, word):
            if (
                r not in range(ROWS)
                or c not in range(COLS)
                or board[r][c] not in node.children
                or node.children[board[r][c]].refs < 1
                or (r, c) in visit
            ):
                return

            visit.add((r, c))
            node = node.children[board[r][c]]
            word += board[r][c]
            if node.isWord:
                node.isWord = False
                res.add(word)
                root.removeWord(word)
                visit.remove((r, c))
                return

            dfs(r + 1, c, node, word)
            dfs(r - 1, c, node, word)
            dfs(r, c + 1, node, word)
            dfs(r, c - 1, node, word)
            visit.remove((r, c))

        for r in range(ROWS):
            for c in range(COLS):
                dfs(r, c, root, "")

        return list(res)
''',
    },
    {
        "id": "search-each-word-separately",
        "mutation": "brute-force",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def findWords(self, board: List[List[str]], words: List[str]) -> List[str]:
        ROWS, COLS = len(board), len(board[0])

        def exist(word):
            path = set()

            def dfs(r, c, i):
                if i == len(word):
                    return True
                if (r not in range(ROWS) or c not in range(COLS)
                        or board[r][c] != word[i] or (r, c) in path):
                    return False
                path.add((r, c))
                found = dfs(r + 1, c, i + 1) or dfs(r - 1, c, i + 1) or dfs(r, c + 1, i + 1) or dfs(r, c - 1, i + 1)
                path.remove((r, c))
                return found

            return any(dfs(r, c, 0) for r in range(ROWS) for c in range(COLS))

        return [word for word in words if exist(word)]
''',
    },
]

CLEAN_VARIANTS = []
