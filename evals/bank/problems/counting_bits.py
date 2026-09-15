from evals.bank.controls import PRELUDE, external_code

NUMBER = 338
SLUG = "counting-bits"
TITLE = "Counting Bits"
DIFFICULTY = "Easy"
SPLIT = "test"
METHOD = "countBits"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    ((2,), [0, 1, 1], "general"),
    ((5,), [0, 1, 1, 2, 1, 2], "general"),
    ((16,), [0, 1, 1, 2, 1, 2, 2, 3, 1, 2, 2, 3, 2, 3, 3, 4, 1], "general"),
    ((0,), [0], "edge"),
    ((1,), [0, 1], "edge"),
]

SCALE = (100_000,)
SPACE_SCALE = (100_000,)


def reference(n):
    return [i.bit_count() for i in range(n + 1)]


def generate(rng):
    # constraints: 0 <= n <= 10^5
    return (rng.choice([rng.randint(0, 64), rng.randint(0, 2000)]),)


def is_edge(n):
    return n <= 1


MUTANTS = [
    {
        "id": "offset-never-moves",
        "mutation": "missing-precondition",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def countBits(self, n: int) -> List[int]:
        dp = [0] * (n + 1)
        offset = 1

        for i in range(1, n + 1):
            dp[i] = 1 + dp[i - offset]
        return dp
''',
    },
    {
        "id": "seeds-one-without-a-guard",
        "mutation": "missing-guard",
        "intended": "edge-case",
        "code": PRELUDE + '''\
class Solution:
    def countBits(self, n: int) -> List[int]:
        dp = [0] * (n + 1)
        dp[1] = 1
        offset = 1

        for i in range(2, n + 1):
            if offset * 2 == i:
                offset = i
            dp[i] = 1 + dp[i - offset]
        return dp
''',
    },
    {
        "id": "thirty-two-bits-each",
        "mutation": "brute-force",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def countBits(self, n: int) -> List[int]:
        res = []
        for i in range(n + 1):
            count = 0
            for bit in range(32):
                count += (i >> bit) & 1
            res.append(count)
        return res
''',
    },
]

CLEAN_VARIANTS = []
