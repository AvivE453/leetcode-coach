NUMBER = 3
SLUG = "longest-substring-without-repeating-characters"
TITLE = "Longest Substring Without Repeating Characters"
DIFFICULTY = "Medium"

CANONICAL = '''\
class Solution:
    def lengthOfLongestSubstring(self, s):
        last = {}
        best = 0
        start = 0
        for i, ch in enumerate(s):
            if ch in last and last[ch] >= start:
                start = last[ch] + 1
            last[ch] = i
            best = max(best, i - start + 1)
        return best
'''

TESTS = [
    (("abcabcbb",), 3, "general"),
    (("bbbbb",), 1, "general"),
    (("pwwkew",), 3, "general"),
    (("abba",), 2, "general"),
    (("",), 0, "edge"),
    ((" ",), 1, "edge"),
]

# All-distinct characters, so a brute force cannot break early out of its inner loop.
SCALE = ("".join(chr(0x4E00 + i) for i in range(2000)),)

MUTANTS = [
    {
        "id": "assumes-nonempty",
        "mutation": "missing-guard",
        "intended": "edge-case",
        "code": '''\
class Solution:
    def lengthOfLongestSubstring(self, s):
        last = {s[0]: 0}
        best = 1
        start = 0
        for i, ch in enumerate(s[1:], start=1):
            if ch in last and last[ch] >= start:
                start = last[ch] + 1
            last[ch] = i
            best = max(best, i - start + 1)
        return best
''',
    },
    {
        "id": "reset-window",
        "mutation": "off-by-one",
        "intended": "bug",
        "code": '''\
class Solution:
    def lengthOfLongestSubstring(self, s):
        last = {}
        best = 0
        start = 0
        for i, ch in enumerate(s):
            if ch in last:
                start = last[ch] + 1
            last[ch] = i
            best = max(best, i - start + 1)
        return best
''',
    },
    {
        "id": "brute-force",
        "mutation": "brute-force",
        "intended": "complexity",
        "code": '''\
class Solution:
    def lengthOfLongestSubstring(self, s):
        best = 0
        for i in range(len(s)):
            seen = set()
            for j in range(i, len(s)):
                if s[j] in seen:
                    break
                seen.add(s[j])
                best = max(best, j - i + 1)
        return best
''',
    },
]
