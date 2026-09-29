from evals.bank.controls import PRELUDE, external_code

NUMBER = 518
SLUG = "coin-change-ii"
TITLE = "Coin Change II"
DIFFICULTY = "Medium"
SPLIT = "test"
METHOD = "change"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    ((5, [1, 2, 5]), 4, "general"),
    ((3, [2]), 0, "general"),
    ((10, [10]), 1, "general"),
    ((7, [2, 3]), 1, "general"),
    ((12, [1, 5, 10]), 4, "general"),
    ((4, [3, 5]), 0, "general"),
    ((0, [7]), 1, "edge"),
]

SCALE = (500, [1, 2, 5, 10, 20, 50, 100, 200])
SPACE_SCALE = (2000, [1, 3, 7])


def reference(amount, coins):
    def ways(i, left):
        if left == 0:
            return 1
        if i == len(coins):
            return 0
        return sum(ways(i + 1, left - uses * coins[i]) for uses in range(left // coins[i] + 1))

    return ways(0, amount)


def valid(amount, coins):
    # 1 <= coins.length <= 300, 1 <= coins[i] <= 5000, coins unique, 0 <= amount <= 5000.
    # Not checked: that the answer fits in 32 bits, which needs the answer itself.
    return (1 <= len(coins) <= 300 and all(1 <= coin <= 5000 for coin in coins)
            and len(set(coins)) == len(coins) and 0 <= amount <= 5000)


def generate(rng):
    return (rng.randint(0, 15), rng.sample(range(1, 9), rng.randint(1, 4)))


MUTANTS = [
    {
        "id": "never-starts-from-zero",
        "mutation": "off-by-one",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def change(self, amount: int, coins: List[int]) -> int:
        dp = [1] + [0] * amount

        for coin in coins:
            for i in range(coin + 1, amount + 1):
                dp[i] += dp[i - coin]

        return dp[amount]
''',
    },
    {
        "id": "recursion-without-memo",
        "mutation": "naive-recursion",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def change(self, amount: int, coins: List[int]) -> int:
        def dfs(i, a):
            if a == amount:
                return 1
            if a > amount or i == len(coins):
                return 0
            return dfs(i, a + coins[i]) + dfs(i + 1, a)

        return dfs(0, 0)
''',
    },
]

CLEAN_VARIANTS = []
