from evals.bank.controls import PRELUDE, external_code

NUMBER = 1888
SLUG = "minimum-number-of-flips-to-make-the-binary-string-alternating"
TITLE = "Minimum Number of Flips to Make the Binary String Alternating"
DIFFICULTY = "Medium"
SPLIT = "test"
METHOD = "minFlips"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    (("111000",), 2, "general"),
    (("010",), 0, "general"),
    (("1110",), 1, "general"),
    (("110",), 0, "general"),
    (("0000",), 2, "general"),
    (("11",), 1, "general"),
    (("0",), 0, "edge"),
    (("1",), 0, "edge"),
]

SCALE = ("1" * 1500 + "0" * 1501,)
SPACE_SCALE = ("1" * 1500 + "0" * 1501,)


def reference(s):
    def flips(t):
        return min(sum(c != "01"[i % 2] for i, c in enumerate(t)), sum(c != "10"[i % 2] for i, c in enumerate(t)))

    return min(flips(s[i:] + s[:i]) for i in range(len(s)))


def valid(s):
    # 1 <= s.length <= 10^5, s[i] is '0' or '1'
    return 1 <= len(s) <= 10**5 and set(s) <= {"0", "1"}


def generate(rng):
    return ("".join(rng.choice("01") for _ in range(rng.randint(1, 10))),)


MUTANTS = [
    {
        "id": "never-rotates",
        "mutation": "missing-precondition",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def minFlips(self, s: str) -> int:
        diff1 = sum(c != ("0" if i % 2 == 0 else "1") for i, c in enumerate(s))
        diff2 = sum(c != ("1" if i % 2 == 0 else "0") for i, c in enumerate(s))
        return min(diff1, diff2)
''',
    },
    {
        "id": "window-one-short",
        "mutation": "off-by-one",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def minFlips(self, s: str) -> int:
        n = len(s)
        s = s + s
        alt1, alt2 = "", ""

        for i in range(len(s)):
            alt1 += "0" if i % 2 == 0 else "1"
            alt2 += "1" if i % 2 == 0 else "0"

        res = float('inf')
        diff1, diff2 = 0, 0
        l = 0
        for r in range(len(s)):
            if s[r] != alt1[r]:
                diff1 += 1
            if s[r] != alt2[r]:
                diff2 += 1
            if (r - l + 1) >= n:
                if s[l] != alt1[l]:
                    diff1 -= 1
                if s[l] != alt2[l]:
                    diff2 -= 1
                l += 1
            if (r - l + 1) == n:
                res = min(res, diff1, diff2)
        return res
''',
    },
    {
        "id": "counts-every-rotation",
        "mutation": "brute-force",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def minFlips(self, s: str) -> int:
        n = len(s)
        best = n
        for i in range(n):
            t = s[i:] + s[:i]
            flips = sum(c != "01"[j % 2] for j, c in enumerate(t))
            best = min(best, flips, n - flips)
        return best
''',
    },
]

CLEAN_VARIANTS = []
