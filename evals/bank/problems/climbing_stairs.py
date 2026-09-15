NUMBER = 70
SLUG = "climbing-stairs"
TITLE = "Climbing Stairs"
DIFFICULTY = "Easy"
SPLIT = "dev"
METHOD = "climbStairs"

CANONICAL = '''\
class Solution:
    def climbStairs(self, n):
        a, b = 1, 1
        for _ in range(n - 1):
            a, b = b, a + b
        return b
'''

TESTS = [
    ((2,), 2, "general"),
    ((3,), 3, "general"),
    ((5,), 8, "general"),
    ((1,), 1, "edge"),
]

SCALE = (32,)
SPACE_SCALE = (45,)


def reference(n):
    ways = {0: 1, 1: 1}

    def count(left):
        if left not in ways:
            ways[left] = count(left - 1) + count(left - 2)
        return ways[left]

    return count(n)


def generate(rng):
    # constraints: 1 <= n <= 45
    return (rng.randint(1, 45),)


def is_edge(n):
    return n <= 2

MUTANTS = [
    {
        "id": "naive-recursion",
        "mutation": "naive-recursion",
        "intended": "complexity",
        "code": '''\
class Solution:
    def climbStairs(self, n):
        if n <= 2:
            return n
        return self.climbStairs(n - 1) + self.climbStairs(n - 2)
''',
    },
    {
        "id": "wrong-at-one",
        "mutation": "wrong-init",
        "intended": "edge-case",
        "code": '''\
class Solution:
    def climbStairs(self, n):
        a, b = 1, 2
        for _ in range(n - 2):
            a, b = b, a + b
        return b
''',
    },
    {
        "id": "off-by-one-base",
        "mutation": "off-by-one",
        "intended": "bug",
        "code": '''\
class Solution:
    def climbStairs(self, n):
        a, b = 1, 1
        for _ in range(n):
            a, b = b, a + b
        return b
''',
    },
]

CLEAN_VARIANTS = [
    {
        "id": "base-cases-first",
        "control": "representative",
        "code": '''\
class Solution:
    def climbStairs(self, n):
        if n <= 2:
            return n
        one_back, two_back = 2, 1
        for _ in range(3, n + 1):
            one_back, two_back = one_back + two_back, one_back
        return one_back
''',
    },
    {
        "id": "linear-at-small-n",
        "control": "regression",
        "probes": "calling a correct O(n) solution suboptimal at the n <= 45 the constraints allow",
        "code": '''\
class Solution:
    def climbStairs(self, n):
        prev, curr = 0, 1
        for _ in range(n):
            prev, curr = curr, prev + curr
        return curr
''',
    },
]
