NUMBER = 322
SLUG = "coin-change"
TITLE = "Coin Change"
DIFFICULTY = "Medium"

CANONICAL = '''\
class Solution:
    def coinChange(self, coins, amount):
        best = [0] + [float("inf")] * amount
        for value in range(1, amount + 1):
            for coin in coins:
                if coin <= value and best[value - coin] + 1 < best[value]:
                    best[value] = best[value - coin] + 1
        return -1 if best[amount] == float("inf") else best[amount]
'''

TESTS = [
    (([1, 2, 5], 11), 3, "general"),
    (([1, 3, 4], 6), 2, "general"),
    (([2], 3), -1, "general"),
    (([1], 0), 0, "edge"),
    (([5], 5), 1, "edge"),
]

SCALE = ([1, 2, 5, 10, 25], 400)

MUTANTS = [
    {
        "id": "greedy-largest-first",
        "mutation": "greedy-substitution",
        "intended": "bug",
        "code": '''\
class Solution:
    def coinChange(self, coins, amount):
        count = 0
        left = amount
        for coin in sorted(coins, reverse=True):
            while left >= coin:
                left -= coin
                count += 1
        return count if left == 0 else -1
''',
    },
    {
        "id": "naive-recursion",
        "mutation": "naive-recursion",
        "intended": "complexity",
        "code": '''\
class Solution:
    def coinChange(self, coins, amount):
        def best(left):
            if left == 0:
                return 0
            if left < 0:
                return float("inf")
            return min([best(left - coin) + 1 for coin in coins], default=float("inf"))

        result = best(amount)
        return -1 if result == float("inf") else result
''',
    },
]
