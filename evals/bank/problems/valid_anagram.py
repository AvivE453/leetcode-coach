NUMBER = 242
SLUG = "valid-anagram"
TITLE = "Valid Anagram"
DIFFICULTY = "Easy"

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
