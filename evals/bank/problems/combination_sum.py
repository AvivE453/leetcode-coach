from evals.bank.controls import PRELUDE, external_code

NUMBER = 39
SLUG = "combination-sum"
TITLE = "Combination Sum"
DIFFICULTY = "Medium"
SPLIT = "dev"
METHOD = "combinationSum"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    (([2, 3, 6, 7], 7), [[2, 2, 3], [7]], "general"),
    (([2, 3, 5], 8), [[2, 2, 2, 2], [2, 3, 3], [3, 5]], "general"),
    (([3, 4], 2), [], "general"),
    (([2], 1), [], "edge"),
    (([7], 7), [[7]], "edge"),
]

SCALE = ([2, 3, 5, 7, 11], 30)
SPACE_SCALE = ([2, 3, 4, 5, 6, 7, 8], 40)


def normalize(combinations):
    """LeetCode accepts the combinations, and the numbers in each, in any order."""
    return sorted(sorted(combination) for combination in combinations)


def reference(candidates, target):
    ways = [[] for _ in range(target + 1)]
    ways[0] = [[]]
    for coin in sorted(candidates):
        for total in range(coin, target + 1):
            ways[total] += [combination + [coin] for combination in ways[total - coin]]
    return ways[target]


def generate(rng):
    # constraints: 1 <= candidates.length <= 30, distinct 2 <= candidates[i] <= 40, 1 <= target <= 40
    return (rng.sample(range(2, 10), rng.randint(1, 4)), rng.randint(1, 15))


MUTANTS = [
    {
        "id": "each-candidate-used-once",
        "mutation": "missing-precondition",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def combinationSum(self, candidates: List[int], target: int) -> List[List[int]]:
        res = []

        def dfs(i, cur, total):
            if total == target:
                res.append(cur.copy())
                return
            if i >= len(candidates) or total > target:
                return

            cur.append(candidates[i])
            dfs(i + 1, cur, total + candidates[i])
            cur.pop()
            dfs(i + 1, cur, total)

        dfs(0, [], 0)
        return res
''',
    },
    {
        "id": "restarts-from-the-first-candidate",
        "mutation": "off-by-one",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def combinationSum(self, candidates: List[int], target: int) -> List[List[int]]:
        res = []

        def dfs(i, cur, total):
            if total == target:
                res.append(cur.copy())
                return
            if i >= len(candidates) or total > target:
                return

            cur.append(candidates[i])
            dfs(0, cur, total + candidates[i])
            cur.pop()
            dfs(i + 1, cur, total)

        dfs(0, [], 0)
        return res
''',
    },
]

CLEAN_VARIANTS = []
