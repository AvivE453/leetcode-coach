from evals.bank.controls import PRELUDE, external_code

NUMBER = 371
SLUG = "sum-of-two-integers"
TITLE = "Sum of Two Integers"
DIFFICULTY = "Medium"
SPLIT = "dev"
METHOD = "getSum"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    ((1, 2), 3, "general"),
    ((2, 3), 5, "general"),
    ((-1, 1), 0, "general"),
    ((-2, -3), -5, "general"),
    ((5, -3), 2, "general"),
    ((0, 0), 0, "edge"),
    ((1000, -1000), 0, "edge"),
    ((-1000, -1000), -2000, "edge"),
]

SCALE = (1000, -999)
SPACE_SCALE = (1000, -999)


def reference(a, b):
    return a + b


def generate(rng):
    # constraints: -1000 <= a, b <= 1000
    return (rng.randint(-1000, 1000), rng.choice([rng.randint(-1000, 1000), rng.randint(-5, 5)]))


MUTANTS = [
    {
        "id": "or-instead-of-xor",
        "mutation": "wrong-operator",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def getSum(self, a: int, b: int) -> int:
        def add(a, b):
            if not a or not b:
                return a or b
            return add(a | b, (a & b) << 1)

        if a * b < 0:  # assume a < 0, b > 0
            if a > 0:
                return self.getSum(b, a)
            if add(~a, 1) == b:  # -a == b
                return 0
            if add(~a, 1) < b:  # -a < b
                return add(~add(add(~a, 1), add(~b, 1)), 1)  # -add(-a, -b)

        return add(a, b)  # a*b >= 0 or (-a) > b > 0
''',
    },
    {
        "id": "carry-not-shifted",
        "mutation": "off-by-one",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def getSum(self, a: int, b: int) -> int:
        def add(a, b):
            if not a or not b:
                return a or b
            return add(a ^ b, a & b)

        if a * b < 0:  # assume a < 0, b > 0
            if a > 0:
                return self.getSum(b, a)
            if add(~a, 1) == b:  # -a == b
                return 0
            if add(~a, 1) < b:  # -a < b
                return add(~add(add(~a, 1), add(~b, 1)), 1)  # -add(-a, -b)

        return add(a, b)  # a*b >= 0 or (-a) > b > 0
''',
    },
]

CLEAN_VARIANTS = []
