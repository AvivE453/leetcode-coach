NUMBER = 121
SLUG = "best-time-to-buy-and-sell-stock"
TITLE = "Best Time to Buy and Sell Stock"
DIFFICULTY = "Easy"
SPLIT = "dev"
METHOD = "maxProfit"

CANONICAL = '''\
class Solution:
    def maxProfit(self, prices):
        best = 0
        cheapest = prices[0]
        for i in range(1, len(prices)):
            best = max(best, prices[i] - cheapest)
            cheapest = min(cheapest, prices[i])
        return best
'''

TESTS = [
    (([7, 1, 5, 3, 6, 4],), 5, "general"),
    (([1, 2, 3, 4, 5],), 4, "general"),
    (([7, 6, 4, 3, 1],), 0, "edge"),
    (([2],), 0, "edge"),
]

SCALE = ([(i * 7919) % 10007 for i in range(3000)],)
SPACE_SCALE = ([(i * 7919) % 10001 for i in range(100_000)],)


def reference(prices):
    best = 0
    for i in range(len(prices)):
        for j in range(i + 1, len(prices)):
            best = max(best, prices[j] - prices[i])
    return best


def generate(rng):
    # constraints: 1 <= prices.length <= 10^5, 0 <= prices[i] <= 10^4
    return ([rng.randint(0, 10) for _ in range(rng.randint(1, 10))],)

MUTANTS = [
    {
        "id": "max-minus-min",
        "mutation": "missing-precondition",
        "intended": "bug",
        "code": '''\
class Solution:
    def maxProfit(self, prices):
        return max(prices) - min(prices)
''',
    },
    {
        "id": "brute-force",
        "mutation": "brute-force",
        "intended": "complexity",
        "code": '''\
class Solution:
    def maxProfit(self, prices):
        best = 0
        for i in range(len(prices)):
            for j in range(i + 1, len(prices)):
                best = max(best, prices[j] - prices[i])
        return best
''',
    },
]

CLEAN_VARIANTS = [
    {
        "id": "track-lowest-price",
        "control": "representative",
        "code": '''\
class Solution:
    def maxProfit(self, prices):
        lowest = float("inf")
        profit = 0
        for price in prices:
            if price < lowest:
                lowest = price
            elif price - lowest > profit:
                profit = price - lowest
        return profit
''',
    },
    {
        "id": "kadane-on-daily-changes",
        "control": "representative",
        "code": '''\
class Solution:
    def maxProfit(self, prices):
        best = run = 0
        for i in range(1, len(prices)):
            run = max(0, run + prices[i] - prices[i - 1])
            best = max(best, run)
        return best
''',
    },
]
