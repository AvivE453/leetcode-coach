from evals.bank.controls import PRELUDE, external_code

NUMBER = 91
SLUG = "decode-ways"
TITLE = "Decode Ways"
DIFFICULTY = "Medium"
SPLIT = "dev"
METHOD = "numDecodings"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    (("12",), 2, "general"),
    (("226",), 3, "general"),
    (("10",), 1, "general"),
    (("27",), 1, "general"),
    (("2101",), 1, "general"),
    (("06",), 0, "edge"),
    (("0",), 0, "edge"),
    (("1",), 1, "edge"),
]

SCALE = ("1" * 26,)
SPACE_SCALE = ("10" * 50,)


def reference(s):
    if not s:
        return 1
    count = 0
    if s[0] != "0":
        count += reference(s[1:])
        if len(s) >= 2 and 10 <= int(s[:2]) <= 26:
            count += reference(s[2:])
    return count


def generate(rng):
    # constraints: 1 <= s.length <= 100, digits only, and the answer fits in 32 bits
    return ("".join(rng.choice("1122203") for _ in range(rng.randint(1, 8))),)


MUTANTS = [
    {
        "id": "twenty-seven-is-a-letter",
        "mutation": "off-by-one",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def numDecodings(self, s: str) -> int:
        # Memoization
        dp = {len(s): 1}

        def dfs(i):
            if i in dp:
                return dp[i]
            if s[i] == "0":
                return 0

            res = dfs(i + 1)
            if i + 1 < len(s) and (
                s[i] == "1" or s[i] == "2" and s[i + 1] in "01234567"
            ):
                res += dfs(i + 2)
            dp[i] = res
            return res

        return dfs(0)
''',
    },
    {
        "id": "zero-can-start-a-letter",
        "mutation": "missing-guard",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def numDecodings(self, s: str) -> int:
        # Memoization
        dp = {len(s): 1}

        def dfs(i):
            if i in dp:
                return dp[i]

            res = dfs(i + 1)
            if i + 1 < len(s) and (
                s[i] == "1" or s[i] == "2" and s[i + 1] in "0123456"
            ):
                res += dfs(i + 2)
            dp[i] = res
            return res

        return dfs(0)
''',
    },
    {
        "id": "recursion-without-memo",
        "mutation": "naive-recursion",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def numDecodings(self, s: str) -> int:
        def dfs(i):
            if i == len(s):
                return 1
            if s[i] == "0":
                return 0

            res = dfs(i + 1)
            if i + 1 < len(s) and (
                s[i] == "1" or s[i] == "2" and s[i + 1] in "0123456"
            ):
                res += dfs(i + 2)
            return res

        return dfs(0)
''',
    },
]

CLEAN_VARIANTS = []
