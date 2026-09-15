from evals.bank.controls import PRELUDE, external_code

NUMBER = 191
SLUG = "number-of-1-bits"
TITLE = "Number of 1 Bits"
DIFFICULTY = "Easy"
SPLIT = "test"
METHOD = "hammingWeight"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    ((11,), 3, "general"),
    ((128,), 1, "general"),
    ((255,), 8, "general"),
    ((2147483645,), 30, "general"),
    ((1,), 1, "edge"),
    ((2**31 - 1,), 31, "edge"),
]

SCALE = (2**31 - 1,)
SPACE_SCALE = (2**31 - 1,)


def reference(n):
    return n.bit_count()


def generate(rng):
    # constraints: 1 <= n <= 2^31 - 1
    return (rng.choice([rng.randint(1, 2**31 - 1), rng.randint(1, 300), 2 ** rng.randint(0, 30)]),)


MUTANTS = [
    {
        "id": "count-from-one",
        "mutation": "wrong-init",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def hammingWeight(self, n: int) -> int:
        res = 1
        while n:
            n &= n - 1
            res += 1
        return res
''',
    },
    {
        "id": "thirty-bits",
        "mutation": "off-by-one",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def hammingWeight(self, n: int) -> int:
        res = 0
        for i in range(30):
            res += (n >> i) & 1
        return res
''',
    },
]

CLEAN_VARIANTS = []
