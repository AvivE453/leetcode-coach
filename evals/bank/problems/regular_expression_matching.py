import re

NUMBER = 10
SLUG = "regular-expression-matching"
TITLE = "Regular Expression Matching"
DIFFICULTY = "Hard"
SPLIT = "dev"
METHOD = "isMatch"

# NeetCode's file defines class Solution twice, so it was rejected and this one is authored.
CANONICAL = '''\
class Solution:
    def isMatch(self, s, p):
        dp = [[False] * (len(p) + 1) for _ in range(len(s) + 1)]
        dp[len(s)][len(p)] = True
        for i in range(len(s), -1, -1):
            for j in range(len(p) - 1, -1, -1):
                first = i < len(s) and p[j] in (s[i], ".")
                if j + 1 < len(p) and p[j + 1] == "*":
                    dp[i][j] = dp[i][j + 2] or (first and dp[i + 1][j])
                else:
                    dp[i][j] = first and dp[i + 1][j + 1]
        return dp[0][0]
'''

TESTS = [
    (("aa", "a"), False, "general"),
    (("aa", "a*"), True, "general"),
    (("ab", ".*"), True, "general"),
    (("aab", "c*a*b"), True, "general"),
    (("mississippi", "mis*is*p*."), False, "general"),
    (("a", "ab*"), True, "general"),
    (("ab", ".*c"), False, "general"),
    (("a", "."), True, "edge"),
]

SCALE = ("a" * 14, "a*" * 7 + "b")
SPACE_SCALE = ("a" * 20, "a*" * 9 + "b")


def reference(s, p):
    return re.fullmatch(p, s) is not None


def generate(rng):
    # constraints: 1 <= s.length, p.length <= 20; s is lowercase letters; p is lowercase letters,
    # "." and "*", and every "*" follows a letter or "."
    s = "".join(rng.choice("ab") for _ in range(rng.randint(1, 5)))
    p = "".join(rng.choice("ab.") + ("*" if rng.random() < 0.4 else "") for _ in range(rng.randint(1, 4)))
    return (s, p)


MUTANTS = [
    {
        "id": "star-needs-at-least-one-copy",
        "mutation": "missing-precondition",
        "intended": "bug",
        "code": '''\
class Solution:
    def isMatch(self, s, p):
        dp = [[False] * (len(p) + 1) for _ in range(len(s) + 1)]
        dp[len(s)][len(p)] = True
        for i in range(len(s), -1, -1):
            for j in range(len(p) - 1, -1, -1):
                first = i < len(s) and p[j] in (s[i], ".")
                if j + 1 < len(p) and p[j + 1] == "*":
                    dp[i][j] = first and dp[i + 1][j]
                else:
                    dp[i][j] = first and dp[i + 1][j + 1]
        return dp[0][0]
''',
    },
    {
        "id": "dot-matches-only-a-dot",
        "mutation": "wrong-operator",
        "intended": "bug",
        "code": '''\
class Solution:
    def isMatch(self, s, p):
        dp = [[False] * (len(p) + 1) for _ in range(len(s) + 1)]
        dp[len(s)][len(p)] = True
        for i in range(len(s), -1, -1):
            for j in range(len(p) - 1, -1, -1):
                first = i < len(s) and p[j] == s[i]
                if j + 1 < len(p) and p[j + 1] == "*":
                    dp[i][j] = dp[i][j + 2] or (first and dp[i + 1][j])
                else:
                    dp[i][j] = first and dp[i + 1][j + 1]
        return dp[0][0]
''',
    },
    {
        "id": "recursion-without-memo",
        "mutation": "naive-recursion",
        "intended": "complexity",
        "code": '''\
class Solution:
    def isMatch(self, s, p):
        def match(i, j):
            if j == len(p):
                return i == len(s)
            first = i < len(s) and p[j] in (s[i], ".")
            if j + 1 < len(p) and p[j + 1] == "*":
                return match(i, j + 2) or (first and match(i + 1, j))
            return first and match(i + 1, j + 1)

        return match(0, 0)
''',
    },
]

CLEAN_VARIANTS = []
