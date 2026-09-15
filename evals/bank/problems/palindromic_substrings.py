from evals.bank.controls import PRELUDE, external_code

NUMBER = 647
SLUG = "palindromic-substrings"
TITLE = "Palindromic Substrings"
DIFFICULTY = "Medium"
SPLIT = "dev"
METHOD = "countSubstrings"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    (("abc",), 3, "general"),
    (("aaa",), 6, "general"),
    (("abba",), 6, "general"),
    (("ab",), 2, "general"),
    (("a",), 1, "edge"),
]

SCALE = ("a" * 200,)
SPACE_SCALE = ("a" * 1000,)


def reference(s):
    return sum(s[i:j] == s[i:j][::-1] for i in range(len(s)) for j in range(i + 1, len(s) + 1))


def generate(rng):
    # constraints: 1 <= s.length <= 1000, lowercase English letters
    return ("".join(rng.choice("ab") for _ in range(rng.randint(1, 8))),)


MUTANTS = [
    {
        "id": "odd-length-centres-only",
        "mutation": "missing-precondition",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def countSubstrings(self, s: str) -> int:
        res = 0

        for i in range(len(s)):
            res += self.countPali(s, i, i)
        return res

    def countPali(self, s, l, r):
        res = 0
        while l >= 0 and r < len(s) and s[l] == s[r]:
            res += 1
            l -= 1
            r += 1
        return res
''',
    },
    {
        "id": "even-centres-skip-a-letter",
        "mutation": "off-by-one",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def countSubstrings(self, s: str) -> int:
        res = 0

        for i in range(len(s)):
            res += self.countPali(s, i, i)
            res += self.countPali(s, i, i + 2)
        return res

    def countPali(self, s, l, r):
        res = 0
        while l >= 0 and r < len(s) and s[l] == s[r]:
            res += 1
            l -= 1
            r += 1
        return res
''',
    },
    {
        "id": "check-every-substring",
        "mutation": "brute-force",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def countSubstrings(self, s: str) -> int:
        res = 0
        for i in range(len(s)):
            for j in range(i, len(s)):
                l, r = i, j
                while l < r and s[l] == s[r]:
                    l += 1
                    r -= 1
                if l >= r:
                    res += 1
        return res
''',
    },
]

CLEAN_VARIANTS = []
