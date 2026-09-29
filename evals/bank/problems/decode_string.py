import re

from evals.bank.controls import PRELUDE, external_code

NUMBER = 394
SLUG = "decode-string"
TITLE = "Decode String"
DIFFICULTY = "Medium"
SPLIT = "test"
METHOD = "decodeString"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    (("3[a]2[bc]",), "aaabcbc", "general"),
    (("3[a2[c]]",), "accaccacc", "general"),
    (("2[abc]3[cd]ef",), "abcabccdcdcdef", "general"),
    (("10[a]",), "a" * 10, "general"),
    (("2[a2[b]]",), "abbabb", "general"),
    (("100[ab]",), "ab" * 100, "general"),
    (("abc",), "abc", "edge"),
    (("a",), "a", "edge"),
]

# At most 30 characters, so no way of building the output is slower in a way that matters,
# and the problem has no complexity mutant.
SCALE = ("300[a2[b3[c]]]",)
SPACE_SCALE = ("300[a2[b3[c]]]",)

INNERMOST = re.compile(r"(\d+)\[([a-z]*)\]")


def reference(s):
    while "[" in s:
        s = INNERMOST.sub(lambda match: int(match[1]) * match[2], s)
    return s


def valid(s):
    # 1 <= s.length <= 30, lowercase letters, digits and brackets, a valid encoding
    # whose repeat counts are in [1, 300]
    if not 1 <= len(s) <= 30 or any(int(k) < 1 or int(k) > 300 for k in re.findall(r"\d+", s)):
        return False
    while INNERMOST.search(s):
        s = INNERMOST.sub(r"\2", s)
    return s.isalpha() and s.islower()


def generate(rng):
    def encoded(depth):
        parts = []
        for _ in range(rng.randint(1, 3)):
            if depth and rng.random() < 0.5:
                parts.append(f"{rng.choice([1, 2, 3, 12])}[{encoded(depth - 1)}]")
            else:
                parts.append(rng.choice("ab"))
        return "".join(parts)

    while True:
        s = encoded(2)
        if len(s) <= 30:
            return (s,)


MUTANTS = [
    {
        "id": "reads-one-digit-of-the-count",
        "mutation": "weaker-structure",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def decodeString(self, s: str) -> str:
        stack = []

        for char in s:
            if char != "]":
                stack.append(char)
            else:
                sub_str = ""
                while stack[-1] != "[":
                    sub_str = stack.pop() + sub_str
                stack.pop()

                multiplier = stack.pop()
                stack.append(int(multiplier) * sub_str)

        return "".join(stack)
''',
    },
    {
        "id": "prepends-the-repeat",
        "mutation": "wrong-operator",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def decodeString(self, s: str) -> str:
        stack = []
        currStr = ''
        currNum = 0

        for c in s:
            if c.isdigit():
                currNum = currNum * 10 + int(c)
            elif c == '[':
                stack.append((currStr, currNum))
                currStr = ''
                currNum = 0
            elif c == ']':
                prevStr, num = stack.pop()
                currStr = num * currStr + prevStr
            else:
                currStr += c

        return currStr
''',
    },
]

CLEAN_VARIANTS = []
