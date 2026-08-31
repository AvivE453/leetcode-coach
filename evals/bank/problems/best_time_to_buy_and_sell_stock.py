NUMBER = 121
SLUG = "best-time-to-buy-and-sell-stock"
TITLE = "Best Time to Buy and Sell Stock"
DIFFICULTY = "Easy"

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
