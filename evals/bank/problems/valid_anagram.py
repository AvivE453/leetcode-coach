NUMBER = 242
SLUG = "valid-anagram"
TITLE = "Valid Anagram"
DIFFICULTY = "Easy"
SPLIT = "dev"
METHOD = "isAnagram"

CANONICAL = '''\
class Solution:
    def isAnagram(self, s, t):
        if len(s) != len(t):
            return False
        counts = {}
        for ch in s:
            counts[ch] = counts.get(ch, 0) + 1
        for ch in t:
            if counts.get(ch, 0) == 0:
                return False
            counts[ch] -= 1
        return True
'''

TESTS = [
    ((("anagram", "nagaram")), True, "general"),
    ((("rat", "car")), False, "general"),
    ((("aab", "abb")), False, "general"),
    # constraints: 1 <= s.length, so a pair of empty strings is not a valid input.
    # Different-length strings are an ordinary input for an anagram check, not a
    # degenerate one - marking them "edge" was a labelling error.
    ((("a", "ab")), False, "general"),
    ((("ab", "a")), False, "general"),
]

SCALE = ("ab" * 40000, "ba" * 40000)
SPACE_SCALE = ("ab" * 25_000, "ba" * 25_000)


def reference(s, t):
    return sorted(s) == sorted(t)


def generate(rng):
    # constraints: 1 <= s.length, t.length <= 5 * 10^4; lowercase English letters
    def word():
        return "".join(rng.choice("abc") for _ in range(rng.randint(1, 8)))

    return (word(), word())

MUTANTS = [
    {
        "id": "set-comparison",
        "mutation": "weaker-structure",
        "intended": "bug",
        "code": '''\
class Solution:
    def isAnagram(self, s, t):
        return set(s) == set(t)
''',
    },
    {
        "id": "no-length-check",
        "mutation": "missing-guard",
        "intended": "edge-case",
        "code": '''\
class Solution:
    def isAnagram(self, s, t):
        counts = {}
        for ch in s:
            counts[ch] = counts.get(ch, 0) + 1
        for ch in t:
            if counts.get(ch, 0) == 0:
                return False
            counts[ch] -= 1
        return True
''',
    },
]

CLEAN_VARIANTS = [
    {
        "id": "counter-equality",
        "control": "representative",
        "code": '''\
from collections import Counter


class Solution:
    def isAnagram(self, s, t):
        return Counter(s) == Counter(t)
''',
    },
    {
        "id": "one-dict-both-strings",
        "control": "representative",
        "code": '''\
class Solution:
    def isAnagram(self, s, t):
        if len(s) != len(t):
            return False
        balance = {}
        for a, b in zip(s, t):
            balance[a] = balance.get(a, 0) + 1
            balance[b] = balance.get(b, 0) - 1
        return all(count == 0 for count in balance.values())
''',
    },
    {
        "id": "lowercase-letter-array",
        "control": "regression",
        "probes": "flagging a guarantee the constraints give (only lowercase English letters)",
        "code": '''\
class Solution:
    def isAnagram(self, s, t):
        if len(s) != len(t):
            return False
        base = ord("a")
        counts = [0] * 26
        for a, b in zip(s, t):
            counts[ord(a) - base] += 1
            counts[ord(b) - base] -= 1
        return not any(counts)
''',
    },
]
