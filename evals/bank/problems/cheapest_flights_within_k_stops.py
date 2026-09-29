from math import inf

from evals.bank.controls import PRELUDE, external_code

NUMBER = 787
SLUG = "cheapest-flights-within-k-stops"
TITLE = "Cheapest Flights Within K Stops"
DIFFICULTY = "Medium"
SPLIT = "test"
METHOD = "findCheapestPrice"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    ((4, [[0, 1, 100], [1, 2, 100], [2, 0, 100], [1, 3, 600], [2, 3, 200]], 0, 3, 1), 700, "general"),
    ((3, [[0, 1, 100], [1, 2, 100], [0, 2, 500]], 0, 2, 1), 200, "general"),
    ((3, [[0, 1, 100], [1, 2, 100], [0, 2, 500]], 0, 2, 0), 500, "general"),
    ((4, [[0, 1, 1], [0, 2, 5], [1, 2, 1], [2, 3, 1]], 0, 3, 1), 6, "general"),
    ((5, [[0, 1, 5], [1, 2, 5], [0, 3, 2], [3, 1, 2], [1, 4, 1], [4, 2, 1]], 0, 2, 2), 7, "general"),
    ((3, [[0, 1, 100]], 0, 2, 1), -1, "general"),
    ((2, [], 0, 1, 0), -1, "edge"),
    ((2, [[0, 1, 5]], 0, 1, 0), 5, "edge"),
]

# Every flight goes to a higher-numbered city, so a search over routes meets every subset
# of the cities in between.
FORWARD = [[i, j, (i * 31 + j * 17) % 100 + 1] for i in range(30) for j in range(i + 1, 30)]
SCALE = (30, FORWARD, 0, 29, 29)
SPACE_SCALE = (30, FORWARD, 0, 29, 29)


def reference(n, flights, src, dst, k):
    best = inf

    def fly(city, cost, legs):
        nonlocal best
        if city == dst:
            best = min(best, cost)
            return
        if legs == k + 1:
            return
        for start, end, price in flights:
            if start == city:
                fly(end, cost + price, legs + 1)

    fly(src, 0, 0)
    return -1 if best == inf else best


def valid(n, flights, src, dst, k):
    # 2 <= n <= 100, 0 <= flights.length <= n(n-1)/2, from != to, both < n,
    # 1 <= price <= 10^4, at most one flight between two cities, 0 <= src, dst, k < n, src != dst
    pairs = {frozenset(flight[:2]) for flight in flights}
    return (2 <= n <= 100 and len(flights) <= n * (n - 1) // 2 and len(pairs) == len(flights)
            and all(len(flight) == 3 and 0 <= flight[0] < n and 0 <= flight[1] < n
                    and flight[0] != flight[1] and 1 <= flight[2] <= 10**4 for flight in flights)
            and 0 <= src < n and 0 <= dst < n and 0 <= k < n and src != dst)


def generate(rng):
    n = rng.randint(2, 5)
    flights = []
    for a in range(n):
        for b in range(a + 1, n):
            if rng.random() < 0.6:
                start, end = (a, b) if rng.random() < 0.5 else (b, a)
                flights.append([start, end, rng.randint(1, 9)])
    src, dst = rng.sample(range(n), 2)
    return (n, flights, src, dst, rng.randint(0, n - 1))


def is_edge(n, flights, src, dst, k):
    return n == 2


MUTANTS = [
    {
        "id": "relaxes-into-the-same-round",
        "mutation": "weaker-structure",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def findCheapestPrice(
        self, n: int, flights: List[List[int]], src: int, dst: int, k: int
    ) -> int:
        prices = [float("inf")] * n
        prices[src] = 0

        for i in range(k + 1):
            for s, d, p in flights:
                if prices[s] == float("inf"):
                    continue
                if prices[s] + p < prices[d]:
                    prices[d] = prices[s] + p
        return -1 if prices[dst] == float("inf") else prices[dst]
''',
    },
    {
        "id": "returns-infinity-when-unreachable",
        "mutation": "missing-guard",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def findCheapestPrice(
        self, n: int, flights: List[List[int]], src: int, dst: int, k: int
    ) -> int:
        prices = [float("inf")] * n
        prices[src] = 0

        for i in range(k + 1):
            tmpPrices = prices.copy()

            for s, d, p in flights:
                if prices[s] == float("inf"):
                    continue
                if prices[s] + p < tmpPrices[d]:
                    tmpPrices[d] = prices[s] + p
            prices = tmpPrices
        return prices[dst]
''',
    },
    {
        "id": "tries-every-route",
        "mutation": "brute-force",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def findCheapestPrice(
        self, n: int, flights: List[List[int]], src: int, dst: int, k: int
    ) -> int:
        graph = defaultdict(list)
        for s, d, p in flights:
            graph[s].append((d, p))
        best = float("inf")

        def dfs(city, cost, stops):
            nonlocal best
            if city == dst:
                best = min(best, cost)
                return
            if stops > k:
                return
            for nxt, price in graph[city]:
                dfs(nxt, cost + price, stops + 1)

        dfs(src, 0, 0)
        return -1 if best == float("inf") else best
''',
    },
]

CLEAN_VARIANTS = []
