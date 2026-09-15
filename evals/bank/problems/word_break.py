from evals.bank.controls import PRELUDE, external_code

NUMBER = 139
SLUG = "word-break"
TITLE = "Word Break"
DIFFICULTY = "Medium"
SPLIT = "dev"
METHOD = "wordBreak"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    (("leetcode", ["leet", "code"]), True, "general"),
    (("applepenapple", ["apple", "pen"]), True, "general"),
    (("catsandog", ["cats", "dog", "sand", "and", "cat"]), False, "general"),
    (("aaab", ["a", "aa"]), False, "general"),
    (("cars", ["car", "ca", "rs"]), True, "general"),
    (("a", ["a"]), True, "edge"),
    (("a", ["b"]), False, "edge"),
]

SCALE = ("a" * 20 + "b", ["a", "aa", "aaa", "aaaa"])
SPACE_SCALE = ("a" * 299 + "b", ["a" * k for k in range(1, 21)])


def reference(s, wordDict):
    return s == "" or any(s.startswith(word) and reference(s[len(word):], wordDict) for word in wordDict)


def generate(rng):
    # constraints: 1 <= s.length <= 300, 1 <= wordDict.length <= 1000, 1 <= word length <= 20,
    # lowercase letters, and the words are unique
    words = sorted({"".join(rng.choice("ab") for _ in range(rng.randint(1, 3))) for _ in range(rng.randint(1, 4))})
    if rng.random() < 0.5:
        s = "".join(rng.choice(words) for _ in range(rng.randint(1, 4)))
    else:
        s = "".join(rng.choice("ab") for _ in range(rng.randint(1, 8)))
    return (s, words)


MUTANTS = [
    {
        "id": "first-matching-word-wins",
        "mutation": "greedy-substitution",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def wordBreak(self, s: str, wordDict: List[str]) -> bool:
        i = 0
        while i < len(s):
            for w in wordDict:
                if s.startswith(w, i):
                    i += len(w)
                    break
            else:
                return False
        return True
''',
    },
    {
        "id": "no-word-may-reach-the-end",
        "mutation": "off-by-one",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def wordBreak(self, s: str, wordDict: List[str]) -> bool:

        dp = [False] * (len(s) + 1)
        dp[len(s)] = True

        for i in range(len(s) - 1, -1, -1):
            for w in wordDict:
                if (i + len(w)) < len(s) and s[i : i + len(w)] == w:
                    dp[i] = dp[i + len(w)]
                if dp[i]:
                    break

        return dp[0]
''',
    },
    {
        "id": "recursion-without-memo",
        "mutation": "naive-recursion",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def wordBreak(self, s: str, wordDict: List[str]) -> bool:
        def breaks(i):
            if i == len(s):
                return True
            return any(s.startswith(w, i) and breaks(i + len(w)) for w in wordDict)

        return breaks(0)
''',
    },
]

CLEAN_VARIANTS = []
