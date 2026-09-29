from evals.bank.controls import PRELUDE, external_code

NUMBER = 97
SLUG = "interleaving-string"
TITLE = "Interleaving String"
DIFFICULTY = "Medium"
SPLIT = "test"
METHOD = "isInterleave"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    (("aabcc", "dbbca", "aadbbcbcac"), True, "general"),
    (("aabcc", "dbbca", "aadbbbaccc"), False, "general"),
    (("ab", "cd", "acbd"), True, "general"),
    (("abc", "def", "abdecf"), True, "general"),
    (("ab", "c", "abcd"), False, "general"),
    (("aab", "aac", "aacaab"), True, "general"),
    (("", "", ""), True, "edge"),
    (("a", "", "a"), True, "edge"),
    (("", "b", "a"), False, "edge"),
]

# No interleaving exists and every letter matches both strings until the last, so a search
# without memo tries every order of the first 99 letters.
SCALE = ("a" * 50, "a" * 50, "a" * 99 + "b")
SPACE_SCALE = ("a" * 100, "a" * 100, "a" * 199 + "b")


def reference(s1, s2, s3):
    if len(s1) + len(s2) != len(s3):
        return False

    def weave(i, j):
        if i == len(s1) and j == len(s2):
            return True
        k = i + j
        return ((i < len(s1) and s1[i] == s3[k] and weave(i + 1, j))
                or (j < len(s2) and s2[j] == s3[k] and weave(i, j + 1)))

    return weave(0, 0)


def valid(s1, s2, s3):
    # 0 <= s1.length, s2.length <= 100, 0 <= s3.length <= 200, lowercase English letters
    return (len(s1) <= 100 and len(s2) <= 100 and len(s3) <= 200
            and all(c.islower() and c.isascii() for c in s1 + s2 + s3))


def generate(rng):
    s1 = "".join(rng.choice("ab") for _ in range(rng.randint(0, 5)))
    s2 = "".join(rng.choice("ab") for _ in range(rng.randint(0, 5)))
    picks = [0] * len(s1) + [1] * len(s2)
    rng.shuffle(picks)
    rest = [list(s1), list(s2)]
    s3 = [rest[pick].pop(0) for pick in picks]
    if s3 and rng.random() < 0.4:
        s3[rng.randrange(len(s3))] = rng.choice("ab")
    if rng.random() < 0.1:
        s3.append("a")
    return (s1, s2, "".join(s3))


def is_edge(s1, s2, s3):
    return not s1 or not s2


MUTANTS = [
    {
        "id": "no-length-check",
        "mutation": "missing-guard",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def isInterleave(self, s1: str, s2: str, s3: str) -> bool:
        dp = [[False] * (len(s2) + 1) for i in range(len(s1) + 1)]
        dp[len(s1)][len(s2)] = True

        for i in range(len(s1), -1, -1):
            for j in range(len(s2), -1, -1):
                if i < len(s1) and s1[i] == s3[i + j] and dp[i + 1][j]:
                    dp[i][j] = True
                if j < len(s2) and s2[j] == s3[i + j] and dp[i][j + 1]:
                    dp[i][j] = True
        return dp[0][0]
''',
    },
    {
        "id": "takes-from-s1-whenever-it-can",
        "mutation": "greedy-substitution",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def isInterleave(self, s1: str, s2: str, s3: str) -> bool:
        if len(s1) + len(s2) != len(s3):
            return False
        i = j = 0
        for c in s3:
            if i < len(s1) and s1[i] == c:
                i += 1
            elif j < len(s2) and s2[j] == c:
                j += 1
            else:
                return False
        return True
''',
    },
    {
        "id": "recursion-without-memo",
        "mutation": "naive-recursion",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def isInterleave(self, s1: str, s2: str, s3: str) -> bool:
        if len(s1) + len(s2) != len(s3):
            return False

        def dfs(i, j):
            if i == len(s1) and j == len(s2):
                return True
            if i < len(s1) and s1[i] == s3[i + j] and dfs(i + 1, j):
                return True
            if j < len(s2) and s2[j] == s3[i + j] and dfs(i, j + 1):
                return True
            return False

        return dfs(0, 0)
''',
    },
]

CLEAN_VARIANTS = []
