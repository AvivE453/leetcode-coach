from evals.bank.controls import PRELUDE, external_code

NUMBER = 190
SLUG = "reverse-bits"
TITLE = "Reverse Bits"
DIFFICULTY = "Easy"
SPLIT = "dev"
METHOD = "reverseBits"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    ((43261596,), 964176192, "general"),
    ((4294967293,), 3221225471, "general"),
    ((0,), 0, "edge"),
    ((1,), 2147483648, "edge"),
    ((2**31,), 1, "edge"),
]

SCALE = (4294967293,)
SPACE_SCALE = (4294967293,)


def reference(n):
    return int(format(n, "032b")[::-1], 2)


def generate(rng):
    # constraints: n is a 32-bit unsigned integer
    return (rng.choice([rng.randint(0, 2**32 - 1), 2 ** rng.randint(0, 31), rng.randint(0, 16)]),)


MUTANTS = [
    {
        "id": "shifts-one-place-short",
        "mutation": "off-by-one",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def reverseBits(self, n: int) -> int:
        res = 0
        for i in range(32):
            bit = (n >> i) & 1
            res += (bit << (30 - i))
        return res
''',
    },
    {
        "id": "puts-each-bit-back-in-place",
        "mutation": "wrong-operator",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def reverseBits(self, n: int) -> int:
        res = 0
        for i in range(32):
            bit = (n >> i) & 1
            res |= (bit << i)
        return res
''',
    },
]

CLEAN_VARIANTS = []
