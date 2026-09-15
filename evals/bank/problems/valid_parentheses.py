NUMBER = 20
SLUG = "valid-parentheses"
TITLE = "Valid Parentheses"
DIFFICULTY = "Easy"
SPLIT = "dev"
METHOD = "isValid"

CANONICAL = '''\
class Solution:
    def isValid(self, s):
        pairs = {")": "(", "]": "[", "}": "{"}
        stack = []
        for ch in s:
            if ch in pairs:
                if not stack or stack.pop() != pairs[ch]:
                    return False
            else:
                stack.append(ch)
        return not stack
'''

TESTS = [
    (("()",), True, "general"),
    (("()[]{}",), True, "general"),
    (("(]",), False, "general"),
    (("([)]",), False, "general"),
    (("{[]}",), True, "general"),
    # An unmatched bracket is a representative invalid input for this problem;
    # only the empty string is a boundary case.
    ((")",), False, "general"),
    (("(",), False, "general"),
    # constraints: 1 <= s.length, so the empty string is not a valid input
]

SCALE = ("()" * 50000,)
SPACE_SCALE = ("(" * 5000 + ")" * 5000,)


def reference(s):
    while True:
        shorter = s.replace("()", "").replace("[]", "").replace("{}", "")
        if shorter == s:
            return s == ""
        s = shorter


def generate(rng):
    # constraints: 1 <= s.length <= 10^4, only the six bracket characters
    return ("".join(rng.choice("()[]{}") for _ in range(rng.randint(1, 10))),)

MUTANTS = [
    {
        "id": "no-underflow-guard",
        "mutation": "missing-guard",
        "intended": "edge-case",
        "code": '''\
class Solution:
    def isValid(self, s):
        pairs = {")": "(", "]": "[", "}": "{"}
        stack = []
        for ch in s:
            if ch in pairs:
                if stack.pop() != pairs[ch]:
                    return False
            else:
                stack.append(ch)
        return not stack
''',
    },
    {
        "id": "no-leftover-check",
        "mutation": "missing-guard",
        "intended": "edge-case",
        "code": '''\
class Solution:
    def isValid(self, s):
        pairs = {")": "(", "]": "[", "}": "{"}
        stack = []
        for ch in s:
            if ch in pairs:
                if not stack or stack.pop() != pairs[ch]:
                    return False
            else:
                stack.append(ch)
        return True
''',
    },
    {
        "id": "count-only",
        "mutation": "weaker-structure",
        "intended": "bug",
        "code": '''\
class Solution:
    def isValid(self, s):
        depth = 0
        for ch in s:
            if ch in "([{":
                depth += 1
            else:
                depth -= 1
                if depth < 0:
                    return False
        return depth == 0
''',
    },
]

CLEAN_VARIANTS = [
    {
        "id": "push-the-expected-closer",
        "control": "representative",
        "code": '''\
class Solution:
    def isValid(self, s):
        closer = {"(": ")", "[": "]", "{": "}"}
        stack = []
        for ch in s:
            if ch in closer:
                stack.append(closer[ch])
            elif not stack or stack.pop() != ch:
                return False
        return not stack
''',
    },
    {
        "id": "odd-length-shortcut",
        "control": "representative",
        "code": '''\
class Solution:
    def isValid(self, s):
        if len(s) % 2:
            return False
        pairs = {")": "(", "]": "[", "}": "{"}
        stack = []
        for ch in s:
            if ch in pairs:
                if not stack or stack.pop() != pairs[ch]:
                    return False
            else:
                stack.append(ch)
        return not stack
''',
    },
]
