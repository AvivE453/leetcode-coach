from evals.bank.controls import PRELUDE, external_code

NUMBER = 424
SLUG = "longest-repeating-character-replacement"
TITLE = "Longest Repeating Character Replacement"
DIFFICULTY = "Medium"
SPLIT = "dev"
METHOD = "characterReplacement"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    (("ABAB", 2), 4, "general"),
    (("AABABBA", 1), 4, "general"),
    (("ABBB", 0), 3, "general"),
    (("ABCDE", 1), 2, "general"),
    (("A", 0), 1, "edge"),
    (("AAAA", 4), 4, "edge"),
]

SCALE = ("ABCD" * 750, 2)
SPACE_SCALE = ("ABCD" * 25_000, 2)


def reference(s, k):
    best = 0
    for i in range(len(s)):
        for j in range(i + 1, len(s) + 1):
            window = s[i:j]
            if len(window) - max(window.count(ch) for ch in set(window)) <= k:
                best = max(best, len(window))
    return best


def generate(rng):
    # constraints: 1 <= s.length <= 10^5, uppercase letters, 0 <= k <= s.length
    s = "".join(rng.choice("ABC") for _ in range(rng.randint(1, 8)))
    return (s, rng.randint(0, len(s)))


MUTANTS = [
    {
        "id": "window-never-shrinks",
        "mutation": "missing-guard",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def characterReplacement(self, s: str, k: int) -> int:
        count = {}

        l = 0
        maxf = 0
        for r in range(len(s)):
            count[s[r]] = 1 + count.get(s[r], 0)
            maxf = max(maxf, count[s[r]])

        return (r - l + 1)
''',
    },
    {
        "id": "budget-used-up-too-early",
        "mutation": "off-by-one",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def characterReplacement(self, s: str, k: int) -> int:
        count = {}

        l = 0
        maxf = 0
        for r in range(len(s)):
            count[s[r]] = 1 + count.get(s[r], 0)
            maxf = max(maxf, count[s[r]])

            if (r - l + 1) - maxf >= k:
                count[s[l]] -= 1
                l += 1

        return (r - l + 1)
''',
    },
    {
        "id": "every-window",
        "mutation": "brute-force",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def characterReplacement(self, s: str, k: int) -> int:
        best = 0
        for l in range(len(s)):
            count = {}
            maxf = 0
            for r in range(l, len(s)):
                count[s[r]] = 1 + count.get(s[r], 0)
                maxf = max(maxf, count[s[r]])
                if (r - l + 1) - maxf <= k:
                    best = max(best, r - l + 1)
        return best
''',
    },
]

CLEAN_VARIANTS = []
