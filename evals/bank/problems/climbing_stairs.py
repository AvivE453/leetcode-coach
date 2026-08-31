NUMBER = 70
SLUG = "climbing-stairs"
TITLE = "Climbing Stairs"
DIFFICULTY = "Easy"

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
