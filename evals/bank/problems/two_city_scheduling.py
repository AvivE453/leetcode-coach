from itertools import combinations

from evals.bank.controls import PRELUDE, external_code

NUMBER = 1029
SLUG = "two-city-scheduling"
TITLE = "Two City Scheduling"
DIFFICULTY = "Medium"
SPLIT = "test"
METHOD = "twoCitySchedCost"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    (([[10, 20], [30, 200], [400, 50], [30, 20]],), 110, "general"),
    (([[259, 770], [448, 54], [926, 667], [184, 139], [840, 118], [577, 469]],), 1859, "general"),
    (([[515, 563], [451, 713], [537, 709], [343, 819], [855, 779], [457, 60], [650, 359], [631, 42]],),
     3086, "general"),
    (([[1, 2], [3, 4]],), 5, "edge"),
    (([[10, 20], [30, 200]],), 50, "edge"),
]

SCALE = ([[(i * 37) % 1000 + 1, (i * 91) % 1000 + 1] for i in range(100)],)
SPACE_SCALE = ([[(i * 37) % 1000 + 1, (i * 91) % 1000 + 1] for i in range(100)],)


def reference(costs):
    people = range(len(costs))
    return min(sum(costs[i][0] if i in to_a else costs[i][1] for i in people)
               for to_a in map(set, combinations(people, len(costs) // 2)))


def valid(costs):
    # 2 <= costs.length <= 100 and even, 1 <= aCost, bCost <= 1000
    return (2 <= len(costs) <= 100 and len(costs) % 2 == 0
            and all(len(cost) == 2 and 1 <= cost[0] <= 1000 and 1 <= cost[1] <= 1000 for cost in costs))


def generate(rng):
    return ([[rng.randint(1, 20), rng.randint(1, 20)] for _ in range(2 * rng.randint(1, 5))],)


MUTANTS = [
    {
        "id": "each-to-the-cheaper-city",
        "mutation": "greedy-substitution",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def twoCitySchedCost(self, costs: List[List[int]]) -> int:
        return sum(min(a, b) for a, b in costs)
''',
    },
    {
        "id": "one-too-many-to-b",
        "mutation": "off-by-one",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def twoCitySchedCost(self, costs: List[List[int]]) -> int:
        diffs = []
        for c1, c2 in costs:
            diffs.append([c2 - c1, c1, c2])
        diffs.sort()
        res = 0
        for i in range(len(diffs)):
            if i <= len(diffs) / 2:
                res += diffs[i][2]
            else:
                res += diffs[i][1]
        return res
''',
    },
    {
        "id": "tries-every-split",
        "mutation": "brute-force",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def twoCitySchedCost(self, costs: List[List[int]]) -> int:
        n = len(costs) // 2
        best = float("inf")
        for group in combinations(range(len(costs)), n):
            chosen = set(group)
            total = sum(costs[i][0] if i in chosen else costs[i][1] for i in range(len(costs)))
            best = min(best, total)
        return best
''',
    },
]

CLEAN_VARIANTS = []
