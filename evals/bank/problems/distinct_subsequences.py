from itertools import combinations

from evals.bank.controls import PRELUDE, external_code

NUMBER = 115
SLUG = "distinct-subsequences"
TITLE = "Distinct Subsequences"
DIFFICULTY = "Hard"
SPLIT = "test"
METHOD = "numDistinct"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    (("rabbbit", "rabbit"), 3, "general"),
    (("babgbag", "bag"), 5, "general"),
    (("aaa", "aa"), 3, "general"),
    (("abc", "d"), 0, "general"),
    (("a", "a"), 1, "edge"),
    (("abc", "abcd"), 0, "edge"),
]

SCALE = ("a" * 20, "a" * 10)
SPACE_SCALE = ("a" * 1000, "b" * 100)


def reference(s, t):
    return sum(all(s[i] == ch for i, ch in zip(chosen, t)) for chosen in combinations(range(len(s)), len(t)))


def generate(rng):
    # constraints: 1 <= s.length, t.length <= 1000, English letters, and the answer fits in 32 bits
    s = "".join(rng.choice("ab") for _ in range(rng.randint(1, 8)))
    t = "".join(rng.choice("ab") for _ in range(rng.randint(1, 4)))
    return (s, t)


MUTANTS = [
    {
        "id": "a-match-must-be-used",
        "mutation": "missing-precondition",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def numDistinct(self, s: str, t: str) -> int:
        cache = {}

        for i in range(len(s) + 1):
            cache[(i, len(t))] = 1
        for j in range(len(t)):
            cache[(len(s), j)] = 0

        for i in range(len(s) - 1, -1, -1):
            for j in range(len(t) - 1, -1, -1):
                if s[i] == t[j]:
                    cache[(i, j)] = cache[(i + 1, j + 1)]
                else:
                    cache[(i, j)] = cache[(i + 1, j)]
        return cache[(0, 0)]
''',
    },
    {
        "id": "base-row-stops-short",
        "mutation": "off-by-one",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def numDistinct(self, s: str, t: str) -> int:
        cache = {}

        for i in range(len(s)):
            cache[(i, len(t))] = 1
        for j in range(len(t)):
            cache[(len(s), j)] = 0

        for i in range(len(s) - 1, -1, -1):
            for j in range(len(t) - 1, -1, -1):
                if s[i] == t[j]:
                    cache[(i, j)] = cache.get((i + 1, j + 1), 0) + cache[(i + 1, j)]
                else:
                    cache[(i, j)] = cache[(i + 1, j)]
        return cache[(0, 0)]
''',
    },
    {
        "id": "recursion-without-memo",
        "mutation": "naive-recursion",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def numDistinct(self, s: str, t: str) -> int:
        def count(i, j):
            if j == len(t):
                return 1
            if i == len(s):
                return 0
            res = count(i + 1, j)
            if s[i] == t[j]:
                res += count(i + 1, j + 1)
            return res

        return count(0, 0)
''',
    },
]

CLEAN_VARIANTS = []
