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
    ((2147483644,), 1073741822, "general"),
    ((0,), 0, "edge"),
    ((2,), 1073741824, "edge"),
    ((2**31 - 2,), 2147483646, "edge"),
]

SCALE = (2**31 - 2,)
SPACE_SCALE = (2**31 - 2,)


def reference(n):
    return int(format(n, "032b")[::-1], 2)


def valid(n):
    # 0 <= n <= 2^31 - 2, n is even
    return 0 <= n <= 2**31 - 2 and n % 2 == 0


def generate(rng):
    # constraints: 0 <= n <= 2^31 - 2, n is even
    return (rng.choice([2 * rng.randint(0, 2**30 - 1), 2 ** rng.randint(1, 30), 2 * rng.randint(0, 8)]),)


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
