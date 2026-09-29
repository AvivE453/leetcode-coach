from itertools import combinations

from evals.bank.controls import PRELUDE, external_code

NUMBER = 1383
SLUG = "maximum-performance-of-a-team"
TITLE = "Maximum Performance of a Team"
DIFFICULTY = "Hard"
SPLIT = "test"
METHOD = "maxPerformance"

CANONICAL = external_code("neetcode", NUMBER)
MOD = 10**9 + 7

TESTS = [
    ((6, [2, 10, 3, 1, 5, 8], [5, 4, 3, 9, 7, 2], 2), 60, "general"),
    ((6, [2, 10, 3, 1, 5, 8], [5, 4, 3, 9, 7, 2], 3), 68, "general"),
    ((6, [2, 10, 3, 1, 5, 8], [5, 4, 3, 9, 7, 2], 4), 72, "general"),
    ((3, [1, 2, 3], [3, 2, 1], 1), 4, "general"),
    ((3, [10, 1, 1], [1, 10, 10], 2), 20, "general"),
    ((1, [5], [3], 1), 15, "edge"),
    ((2, [100000, 100000], [100000000, 100000000], 2), 2 * 10**13 % MOD, "edge"),
]

SCALE = (3000, [(i * 37) % 100_000 + 1 for i in range(3000)], [(i * 91) % 10**8 + 1 for i in range(3000)], 100)
SPACE_SCALE = (3000, [(i * 37) % 100_000 + 1 for i in range(3000)], [(i * 91) % 10**8 + 1 for i in range(3000)], 100)


def reference(n, speed, efficiency, k):
    engineers = list(zip(speed, efficiency))
    return max(sum(s for s, _ in team) * min(e for _, e in team)
               for size in range(1, k + 1) for team in combinations(engineers, size)) % MOD


def valid(n, speed, efficiency, k):
    # 1 <= k <= n <= 10^5, speed.length == efficiency.length == n,
    # 1 <= speed[i] <= 10^5, 1 <= efficiency[i] <= 10^8
    return (1 <= k <= n <= 10**5 and len(speed) == n and len(efficiency) == n
            and all(1 <= s <= 10**5 for s in speed) and all(1 <= e <= 10**8 for e in efficiency))


def generate(rng):
    n = rng.randint(1, 7)
    return (n, [rng.randint(1, 10) for _ in range(n)], [rng.randint(1, 10) for _ in range(n)], rng.randint(1, n))


def is_edge(n, speed, efficiency, k):
    # One engineer, or a team whose performance can reach the modulus.
    return n == 1 or sum(speed) * max(efficiency) >= MOD


MUTANTS = [
    {
        "id": "scores-before-dropping-the-slowest",
        "mutation": "off-by-one",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def maxPerformance(self, n: int, speed: List[int], efficiency: List[int], k: int) -> int:
        MOD = 1_000_000_007
        ans = 0
        speedSum = 0
        A = sorted([(e, s) for s, e in zip(speed, efficiency)], reverse=True)
        minHeap = []

        for e, s in A:
            heapq.heappush(minHeap, s)
            speedSum += s
            ans = max(ans, speedSum * e)
            if len(minHeap) > k:
                speedSum -= heapq.heappop(minHeap)

        return ans % MOD
''',
    },
    {
        "id": "compares-reduced-performances",
        "mutation": "unsafe-arithmetic",
        "intended": "edge-case",
        "code": PRELUDE + '''\
class Solution:
    def maxPerformance(self, n: int, speed: List[int], efficiency: List[int], k: int) -> int:
        mod = 10 ** 9 + 7
        eng = []
        for eff, spd in zip(efficiency, speed):
            eng.append([eff, spd])
        eng.sort(reverse=True)

        res, speed = 0, 0
        minHeap = []

        for eff, spd in eng:
            if len(minHeap) == k:
                speed -= heapq.heappop(minHeap)
            speed += spd
            heapq.heappush(minHeap, spd)
            res = max(res, eff * speed % mod)
        return res
''',
    },
    {
        "id": "sorts-the-faster-engineers-for-each",
        "mutation": "brute-force",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def maxPerformance(self, n: int, speed: List[int], efficiency: List[int], k: int) -> int:
        best = 0
        for i in range(n):
            eligible = sorted((speed[j] for j in range(n)
                               if efficiency[j] >= efficiency[i] and j != i), reverse=True)
            best = max(best, (speed[i] + sum(eligible[:k - 1])) * efficiency[i])
        return best % (10**9 + 7)
''',
    },
]

CLEAN_VARIANTS = []
