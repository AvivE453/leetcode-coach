from evals.bank.controls import PRELUDE, external_code

NUMBER = 125
SLUG = "valid-palindrome"
TITLE = "Valid Palindrome"
DIFFICULTY = "Easy"
SPLIT = "test"
METHOD = "isPalindrome"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    (("A man, a plan, a canal: Panama",), True, "general"),
    (("race a car",), False, "general"),
    (("0P",), False, "general"),
    (("ab_a",), True, "general"),
    ((" ",), True, "edge"),
    (("a.",), True, "edge"),
]

SCALE = ("a" * 10_000 + "b" + "a" * 10_000,)
SPACE_SCALE = ("a" * 100_000 + "b" + "a" * 99_999,)


def reference(s):
    kept = [ch.lower() for ch in s if ch.isalnum()]
    return kept == kept[::-1]


def generate(rng):
    # constraints: 1 <= s.length <= 2 * 10^5, printable ASCII
    core = "".join(rng.choice("ab1") for _ in range(rng.randint(0, 4)))
    tail = core[::-1] if rng.random() < 0.5 else "".join(rng.choice("ab1") for _ in range(rng.randint(0, 4)))
    text = []
    for ch in core + tail:
        text.append(ch.upper() if rng.random() < 0.3 else ch)
        if rng.random() < 0.3:
            text.append(rng.choice(" ,:!"))
    return ("".join(text) or " ",)


def is_edge(s):
    return sum(ch.isalnum() for ch in s) <= 1


MUTANTS = [
    {
        "id": "letters-only",
        "mutation": "weaker-structure",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def isPalindrome(self, s: str) -> bool:
        new = ''
        for a in s:
            if a.isalpha():
                new += a.lower()
        return (new == new[::-1])
''',
    },
    {
        "id": "empty-is-not-a-palindrome",
        "mutation": "missing-guard",
        "intended": "edge-case",
        "code": PRELUDE + '''\
class Solution:
    def isPalindrome(self, s: str) -> bool:
        new = ''
        for a in s:
            if a.isalpha() or a.isdigit():
                new += a.lower()
        if not new:
            return False
        return (new == new[::-1])
''',
    },
    {
        "id": "reverse-every-step",
        "mutation": "brute-force",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def isPalindrome(self, s: str) -> bool:
        new = ''
        for a in s:
            if a.isalpha() or a.isdigit():
                new += a.lower()
        for i in range(len(new)):
            if new[i] != new[::-1][i]:
                return False
        return True
''',
    },
]

CLEAN_VARIANTS = []
