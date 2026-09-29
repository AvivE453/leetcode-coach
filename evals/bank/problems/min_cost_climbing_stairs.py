from evals.bank.controls import PRELUDE, external_code

NUMBER = 746
SLUG = "min-cost-climbing-stairs"
TITLE = "Min Cost Climbing Stairs"
DIFFICULTY = "Easy"
SPLIT = "test"
METHOD = "minCostClimbingStairs"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    (([10, 15, 20],), 15, "general"),
    (([1, 100, 1, 1, 1, 100, 1, 1, 100, 1],), 6, "general"),
    (([0, 0, 0, 1],), 0, "general"),
    (([5, 3, 8, 2, 7],), 5, "general"),
    (([7, 3],), 3, "edge"),
    (([4, 4],), 4, "edge"),
]

SCALE = ([(i * 37) % 1000 for i in range(1000)],)
SPACE_SCALE = ([(i * 37) % 1000 for i in range(1000)],)


def reference(cost):
    top = len(cost)

    def cheapest(step):
        if step >= top:
            return 0
        return cost[step] + min(cheapest(step + 1), cheapest(step + 2))

    return min(cheapest(0), cheapest(1))


def valid(cost):
    # 2 <= cost.length <= 1000, 0 <= cost[i] <= 999
    return 2 <= len(cost) <= 1000 and all(0 <= c <= 999 for c in cost)


def generate(rng):
    return ([rng.randint(0, 9) for _ in range(rng.randint(2, 10))],)


MUTANTS = [
    {
        "id": "takes-the-dearer-next-step",
        "mutation": "wrong-operator",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def minCostClimbingStairs(self, cost: List[int]) -> int:
        for i in range(len(cost) - 3, -1, -1):
            cost[i] += max(cost[i + 1], cost[i + 2])

        return min(cost[0], cost[1])
''',
    },
    {
        "id": "recursion-without-memo",
        "mutation": "naive-recursion",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def minCostClimbingStairs(self, cost: List[int]) -> int:
        def climb(i):
            if i >= len(cost):
                return 0
            return cost[i] + min(climb(i + 1), climb(i + 2))

        return min(climb(0), climb(1))
''',
    },
]

CLEAN_VARIANTS = []
