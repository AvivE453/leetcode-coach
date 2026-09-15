from collections import Counter

from evals.bank.controls import PRELUDE, external_code

NUMBER = 76
SLUG = "minimum-window-substring"
TITLE = "Minimum Window Substring"
DIFFICULTY = "Hard"
SPLIT = "test"
METHOD = "minWindow"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    (("ADOBECODEBANC", "ABC"), "BANC", "general"),
    (("ab", "b"), "b", "general"),
    (("aa", "aa"), "aa", "general"),
    (("abc", "cba"), "abc", "general"),
    (("a", "a"), "a", "edge"),
    (("a", "aa"), "", "edge"),
]

SCALE = ("xyz" * 50 + "ABC", "ABC")
SPACE_SCALE = ("xyz" * 33_332 + "ABC", "ABC")


def covering_windows(s, t):
    need = Counter(t)
    return [(i, j) for i in range(len(s)) for j in range(i + 1, len(s) + 1) if not need - Counter(s[i:j])]


def reference(s, t):
    windows = covering_windows(s, t)
    if not windows:
        return ""
    i, j = min(windows, key=lambda window: window[1] - window[0])
    return s[i:j]


def generate(rng):
    # constraints: 1 <= s.length, t.length <= 10^5, English letters, and the answer is unique
    while True:
        s = "".join(rng.choice("abc") for _ in range(rng.randint(1, 8)))
        t = "".join(rng.choice("abc") for _ in range(rng.randint(1, 3)))
        windows = covering_windows(s, t)
        shortest = min((j - i for i, j in windows), default=0)
        if sum(j - i == shortest for i, j in windows) <= 1:
            return (s, t)


MUTANTS = [
    {
        "id": "needs-each-letter-once",
        "mutation": "weaker-structure",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def minWindow(self, s: str, t: str) -> str:
        if len(s) < len(t):
            return ""

        countT, window = {}, {}
        for c in t:
            countT[c] = 1

        have, need = 0, len(countT)
        res, resLen = [-1, -1], float("infinity")
        l = 0
        for r in range(len(s)):
            c = s[r]
            window[c] = 1 + window.get(c, 0)

            if c in countT and window[c] == countT[c]:
                have += 1

            while have == need:
                # update our result
                if (r - l + 1) < resLen:
                    res = [l, r]
                    resLen = r - l + 1
                # pop from the left of our window
                window[s[l]] -= 1
                if s[l] in countT and window[s[l]] < countT[s[l]]:
                    have -= 1
                l += 1
        l, r = res
        return s[l : r + 1] if resLen != float("infinity") else ""
''',
    },
    {
        "id": "records-after-shrinking",
        "mutation": "off-by-one",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def minWindow(self, s: str, t: str) -> str:
        if len(s) < len(t):
            return ""

        countT, window = {}, {}
        for c in t:
            countT[c] = 1 + countT.get(c, 0)

        have, need = 0, len(countT)
        res, resLen = [-1, -1], float("infinity")
        l = 0
        for r in range(len(s)):
            c = s[r]
            window[c] = 1 + window.get(c, 0)

            if c in countT and window[c] == countT[c]:
                have += 1

            while have == need:
                # pop from the left of our window
                window[s[l]] -= 1
                if s[l] in countT and window[s[l]] < countT[s[l]]:
                    have -= 1
                l += 1
                # update our result
                if (r - l + 1) < resLen:
                    res = [l, r]
                    resLen = r - l + 1
        l, r = res
        return s[l : r + 1] if resLen != float("infinity") else ""
''',
    },
    {
        "id": "every-substring",
        "mutation": "brute-force",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def minWindow(self, s: str, t: str) -> str:
        need = Counter(t)
        best = ""
        for i in range(len(s)):
            for j in range(i + 1, len(s) + 1):
                if (not best or j - i < len(best)) and not need - Counter(s[i:j]):
                    best = s[i:j]
        return best
''',
    },
]

CLEAN_VARIANTS = []
