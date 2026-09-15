from evals.bank.controls import PRELUDE, external_code

NUMBER = 1143
SLUG = "longest-common-subsequence"
TITLE = "Longest Common Subsequence"
DIFFICULTY = "Medium"
SPLIT = "test"
METHOD = "longestCommonSubsequence"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    (("abcde", "ace"), 3, "general"),
    (("abc", "abc"), 3, "general"),
    (("abc", "def"), 0, "general"),
    (("bl", "yby"), 1, "general"),
    (("aa", "a"), 1, "general"),
    (("a", "a"), 1, "edge"),
    (("a", "b"), 0, "edge"),
]

SCALE = ("a" * 12, "b" * 12)
SPACE_SCALE = ("ab" * 500, "ba" * 500)


def reference(text1, text2):
    def is_subsequence(small, big):
        letters = iter(big)
        return all(ch in letters for ch in small)

    best = 0
    for chosen in range(1 << len(text1)):
        sub = "".join(ch for i, ch in enumerate(text1) if chosen >> i & 1)
        if len(sub) > best and is_subsequence(sub, text2):
            best = len(sub)
    return best


def generate(rng):
    # constraints: 1 <= text1.length, text2.length <= 1000, lowercase English letters
    def text():
        return "".join(rng.choice("abc") for _ in range(rng.randint(1, 6)))

    return (text(), text())


MUTANTS = [
    {
        "id": "match-greedily",
        "mutation": "greedy-substitution",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def longestCommonSubsequence(self, text1: str, text2: str) -> int:
        i = j = res = 0
        while i < len(text1) and j < len(text2):
            if text1[i] == text2[j]:
                res += 1
                i += 1
            j += 1
        return res
''',
    },
    {
        "id": "match-extends-the-best-neighbour",
        "mutation": "wrong-operator",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def longestCommonSubsequence(self, text1: str, text2: str) -> int:
        dp = [[0 for j in range(len(text2) + 1)] for i in range(len(text1) + 1)]

        for i in range(len(text1) - 1, -1, -1):
            for j in range(len(text2) - 1, -1, -1):
                if text1[i] == text2[j]:
                    dp[i][j] = 1 + max(dp[i + 1][j], dp[i][j + 1])
                else:
                    dp[i][j] = max(dp[i][j + 1], dp[i + 1][j])

        return dp[0][0]
''',
    },
    {
        "id": "recursion-without-memo",
        "mutation": "naive-recursion",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def longestCommonSubsequence(self, text1: str, text2: str) -> int:
        def lcs(i, j):
            if i == len(text1) or j == len(text2):
                return 0
            if text1[i] == text2[j]:
                return 1 + lcs(i + 1, j + 1)
            return max(lcs(i + 1, j), lcs(i, j + 1))

        return lcs(0, 0)
''',
    },
]

CLEAN_VARIANTS = []
