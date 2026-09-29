from math import gcd

from evals.bank.controls import PRELUDE, external_code

NUMBER = 2709
SLUG = "greatest-common-divisor-traversal"
TITLE = "Greatest Common Divisor Traversal"
DIFFICULTY = "Hard"
SPLIT = "test"
METHOD = "canTraverseAllPairs"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    (([2, 3, 6],), True, "general"),
    (([3, 9, 5],), False, "general"),
    (([4, 3, 12, 8],), True, "general"),
    (([1, 1],), False, "general"),
    (([2, 4, 1],), False, "general"),
    (([10, 15, 6],), True, "general"),
    (([99991, 99991],), True, "general"),
    (([1],), True, "edge"),
    (([7],), True, "edge"),
]

SCALE = ([2 * (i % 500 + 1) for i in range(2000)],)
SPACE_SCALE = ([(i % 50_000) + 50_000 for i in range(10**4)],)


def reference(nums):
    reached = {0}
    frontier = [0]
    while frontier:
        i = frontier.pop()
        for j in range(len(nums)):
            if j not in reached and gcd(nums[i], nums[j]) > 1:
                reached.add(j)
                frontier.append(j)
    return len(reached) == len(nums)


def valid(nums):
    # 1 <= nums.length <= 10^5, 1 <= nums[i] <= 10^5
    return 1 <= len(nums) <= 10**5 and all(1 <= x <= 10**5 for x in nums)


def generate(rng):
    return ([rng.randint(1, 30) for _ in range(rng.randint(1, 7))],)


def is_edge(nums):
    return len(nums) == 1


MUTANTS = [
    {
        "id": "last-prime-factor-dropped",
        "mutation": "missing-guard",
        "intended": "bug",
        "code": PRELUDE + '''\
class UnionFind:
    def __init__(self, n):
        self.par = [i for i in range(n)]
        self.size = [1] * n
        self.count = n

    def find(self, x):
        if self.par[x] != x:
            self.par[x] = self.find(self.par[x])
        return self.par[x]

    def union(self, x, y):
        px, py = self.find(x), self.find(y)
        if px == py:
            return
        if self.size[px] < self.size[py]:
            self.par[px] = py
            self.size[py] += self.size[px]
        else:
            self.par[py] = px
            self.size[px] += self.size[py]
        self.count -= 1


class Solution:
    def canTraverseAllPairs(self, nums: List[int]) -> bool:
        uf = UnionFind(len(nums))

        factor_index = {}
        for i, n in enumerate(nums):
            f = 2
            while f * f <= n:
                if n % f == 0:
                    if f in factor_index:
                        uf.union(i, factor_index[f])
                    else:
                        factor_index[f] = i
                    while n % f == 0:
                        n = n // f
                f += 1
        return uf.count == 1
''',
    },
    {
        "id": "any-one-means-false",
        "mutation": "missing-guard",
        "intended": "edge-case",
        "code": PRELUDE + '''\
class Solution:
    def canTraverseAllPairs(self, nums: List[int]) -> bool:
        if 1 in nums:
            return False
        parent = list(range(len(nums)))

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        first_with = {}
        for i, num in enumerate(nums):
            f = 2
            while f * f <= num:
                if num % f == 0:
                    if f in first_with:
                        parent[find(i)] = find(first_with[f])
                    else:
                        first_with[f] = i
                    while num % f == 0:
                        num //= f
                f += 1
            if num > 1:
                if num in first_with:
                    parent[find(i)] = find(first_with[num])
                else:
                    first_with[num] = i
        return len({find(i) for i in range(len(nums))}) == 1
''',
    },
    {
        "id": "gcd-of-every-pair",
        "mutation": "brute-force",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def canTraverseAllPairs(self, nums: List[int]) -> bool:
        n = len(nums)
        seen = {0}
        stack = [0]
        while stack:
            i = stack.pop()
            for j in range(n):
                if j not in seen and math.gcd(nums[i], nums[j]) > 1:
                    seen.add(j)
                    stack.append(j)
        return len(seen) == n
''',
    },
]

CLEAN_VARIANTS = []
