from evals.bank.controls import PRELUDE, external_code

NUMBER = 50
SLUG = "powx-n"
TITLE = "Pow(x, n)"
DIFFICULTY = "Medium"
SPLIT = "dev"
METHOD = "myPow"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    ((2.0, 10), 1024.0, "general"),
    ((2.1, 3), 9.261, "general"),
    ((2.0, -2), 0.25, "general"),
    ((-2.0, 3), -8.0, "general"),
    ((5.0, 0), 1.0, "edge"),
    ((0.0, 5), 0.0, "edge"),
    ((1.0, 1000), 1.0, "edge"),
]

SCALE = (1.0, 1_000_000)
SPACE_SCALE = (2.0, 13)


def normalize(value):
    """LeetCode accepts an answer within 10^-5, and floating products drift in the last bits."""
    return round(value, 5)


def reference(x, n):
    return x**n


def generate(rng):
    # constraints: -100 < x < 100, -2^31 <= n <= 2^31 - 1, x != 0 or n > 0, -10^4 <= x^n <= 10^4
    while True:
        x = rng.choice([-3.0, -2.5, -2.0, -1.5, -1.0, -0.5, 0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0])
        n = rng.randint(-6, 6)
        if (x != 0 or n > 0) and abs(x**n) <= 10**4:
            return (x, n)


MUTANTS = [
    {
        "id": "negative-exponent-ignored",
        "mutation": "missing-precondition",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def myPow(self, x: float, n: int) -> float:
        def helper(x, n):
            if x == 0:
                return 0
            if n == 0:
                return 1

            res = helper(x * x, n // 2)
            return x * res if n % 2 else res

        return helper(x, abs(n))
''',
    },
    {
        "id": "odd-and-even-swapped",
        "mutation": "wrong-operator",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def myPow(self, x: float, n: int) -> float:
        def helper(x, n):
            if x == 0:
                return 0
            if n == 0:
                return 1

            res = helper(x * x, n // 2)
            return res if n % 2 else x * res

        res = helper(x, abs(n))
        return res if n >= 0 else 1 / res
''',
    },
    {
        "id": "multiply-n-times",
        "mutation": "brute-force",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def myPow(self, x: float, n: int) -> float:
        res = 1.0
        for _ in range(abs(n)):
            res *= x
        return res if n >= 0 else 1 / res
''',
    },
]

CLEAN_VARIANTS = []
