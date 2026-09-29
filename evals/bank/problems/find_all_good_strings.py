from itertools import product
from string import ascii_lowercase

from evals.bank.controls import PRELUDE, external_code

NUMBER = 1397
SLUG = "find-all-good-strings"
TITLE = "Find All Good Strings"
DIFFICULTY = "Hard"
SPLIT = "test"
METHOD = "findGoodStrings"

CANONICAL = external_code("neetcode", NUMBER)

# Not LeetCode's second example: at n = 8 the reference would have to enumerate 26^8
# strings to check its expectation, and a test nothing can check is only a claim.
TESTS = [
    ((2, "aa", "da", "b"), 51, "general"),
    ((2, "gx", "gz", "x"), 2, "general"),
    ((1, "a", "z", "b"), 25, "general"),
    ((2, "az", "bb", "a"), 1, "general"),
    ((3, "aaa", "aaz", "aab"), 25, "general"),
    ((4, "aaaa", "aabz", "aab"), 25, "general"),
    ((1, "a", "a", "a"), 0, "edge"),
    ((3, "aaa", "zzz", "abcd"), 26**3, "edge"),
]

SCALE = (60, "a" * 60, "z" * 60, "abab")
SPACE_SCALE = (500, "a" * 500, "z" * 500, "abcab")
# Each draw enumerates every string of its length, up to 26^3 of them.
DIFFERENTIAL_CASES = 200


def reference(n, s1, s2, evil):
    strings = ("".join(letters) for letters in product(ascii_lowercase, repeat=n))
    return sum(s1 <= s <= s2 and evil not in s for s in strings) % (10**9 + 7)


def valid(n, s1, s2, evil):
    # s1.length == s2.length == n, s1 <= s2, 1 <= n <= 500, 1 <= evil.length <= 50, lowercase
    return (1 <= n <= 500 and len(s1) == n and len(s2) == n and s1 <= s2 and 1 <= len(evil) <= 50
            and all(c in ascii_lowercase for c in s1 + s2 + evil))


def generate(rng):
    n = rng.randint(1, 3)
    s1, s2 = sorted("".join(rng.choice("abcxyz") for _ in range(n)) for _ in range(2))
    evil = "".join(rng.choice("ab") for _ in range(rng.randint(1, 3)))
    return (n, s1, s2, evil)


MUTANTS = [
    {
        "id": "leaves-out-s1",
        "mutation": "off-by-one",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def findGoodStrings(self, n: int, s1: str, s2: str, evil: str) -> int:
        a = ord('a')
        z = ord('z')

        arr_e = list(map(ord, evil))
        len_e = len(evil)
        next = [0] * len_e

        for i in range(1, len_e):
            j = next[i - 1]
            while j > 0 and evil[i] != evil[j]:
                j = next[j - 1]
            if evil[i] == evil[j]:
                next[i] = j + 1

        def good(s):
            arr = list(map(ord, s))
            len_a = len(arr)

            @cache
            def f(i, skip, reach, e):
                if e == len_e:
                    return 0
                if i == len_a:
                    return 0 if skip else 1

                limit = arr[i] if reach else z
                ans = 0

                if skip:
                    ans += f(i + 1, True, False, 0)

                for c in range(a, limit + 1):
                    ee = e
                    while ee > 0 and arr_e[ee] != c:
                        ee = next[ee - 1]

                    if arr_e[ee] == c:
                        ee += 1

                    ans += f(i + 1, False, reach and c == limit, ee)

                return ans % int(1e9 + 7)

            return f(0, True, True, 0)

        return (good(s2) - good(s1)) % int(1e9 + 7)
''',
    },
    {
        "id": "match-restarts-from-scratch",
        "mutation": "weaker-structure",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def findGoodStrings(self, n: int, s1: str, s2: str, evil: str) -> int:
        MOD = 1_000_000_007

        @functools.lru_cache(None)
        def dp(i: int, matched: int, isS1Prefix: bool, isS2Prefix: bool) -> int:
            if matched == len(evil):
                return 0
            if i == n:
                return 1
            ans = 0
            lo = ord(s1[i]) if isS1Prefix else ord('a')
            hi = ord(s2[i]) if isS2Prefix else ord('z')
            for charIndex in range(lo, hi + 1):
                c = chr(charIndex)
                if evil[matched] == c:
                    nextMatched = matched + 1
                else:
                    nextMatched = 1 if evil[0] == c else 0
                ans += dp(i + 1, nextMatched, isS1Prefix and c == s1[i], isS2Prefix and c == s2[i])
                ans %= MOD
            return ans

        return dp(0, 0, True, True)
''',
    },
    {
        "id": "recursion-without-memo",
        "mutation": "naive-recursion",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def findGoodStrings(self, n: int, s1: str, s2: str, evil: str) -> int:
        MOD = 1_000_000_007
        lps = [0] * len(evil)
        j = 0
        for i in range(1, len(evil)):
            while j > 0 and evil[j] != evil[i]:
                j = lps[j - 1]
            if evil[i] == evil[j]:
                j += 1
                lps[i] = j

        def advance(matched, c):
            while matched > 0 and evil[matched] != c:
                matched = lps[matched - 1]
            return matched + 1 if evil[matched] == c else matched

        def dp(i, matched, tightLow, tightHigh):
            if matched == len(evil):
                return 0
            if i == n:
                return 1
            lo = ord(s1[i]) if tightLow else ord('a')
            hi = ord(s2[i]) if tightHigh else ord('z')
            total = 0
            for code in range(lo, hi + 1):
                c = chr(code)
                total += dp(i + 1, advance(matched, c), tightLow and c == s1[i], tightHigh and c == s2[i])
            return total % MOD

        return dp(0, 0, True, True)
''',
    },
]

CLEAN_VARIANTS = []
