from itertools import product

from evals.bank.controls import PRELUDE

NUMBER = 1049
SLUG = "last-stone-weight-ii"
TITLE = "Last Stone Weight II"
DIFFICULTY = "Medium"
SPLIT = "test"
METHOD = "lastStoneWeightII"

# NeetCode's file calls ceil without importing it, so it fails its first test and was
# rejected; this one is authored: in the test split it is the timing reference for the
# mutants, not a control.
CANONICAL = PRELUDE + '''\
class Solution:
    def lastStoneWeightII(self, stones: List[int]) -> int:
        total = sum(stones)
        reachable = {0}
        for stone in stones:
            reachable |= {weight + stone for weight in reachable}
        return min(abs(total - 2 * weight) for weight in reachable)
'''

TESTS = [
    (([2, 7, 4, 1, 8, 1],), 1, "general"),
    (([31, 26, 33, 21, 40],), 5, "general"),
    (([1, 1],), 0, "general"),
    (([1, 2],), 1, "general"),
    (([3, 3, 3],), 3, "general"),
    (([7],), 7, "edge"),
    (([100],), 100, "edge"),
]

SCALE = ([(i * 37) % 100 + 1 for i in range(30)],)
SPACE_SCALE = ([(i * 37) % 100 + 1 for i in range(30)],)


def reference(stones):
    total = sum(stones)
    return min(abs(total - 2 * sum(stone for stone, taken in zip(stones, picks) if taken))
               for picks in product((False, True), repeat=len(stones)))


def valid(stones):
    # 1 <= stones.length <= 30, 1 <= stones[i] <= 100
    return 1 <= len(stones) <= 30 and all(1 <= stone <= 100 for stone in stones)


def generate(rng):
    return ([rng.randint(1, 20) for _ in range(rng.randint(1, 10))],)


MUTANTS = [
    {
        "id": "smashes-the-two-heaviest",
        "mutation": "greedy-substitution",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def lastStoneWeightII(self, stones: List[int]) -> int:
        heap = [-stone for stone in stones]
        heapq.heapify(heap)
        while len(heap) > 1:
            y = -heapq.heappop(heap)
            x = -heapq.heappop(heap)
            if y != x:
                heapq.heappush(heap, -(y - x))
        return -heap[0] if heap else 0
''',
    },
    {
        "id": "recursion-without-memo",
        "mutation": "naive-recursion",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def lastStoneWeightII(self, stones: List[int]) -> int:
        stoneSum = sum(stones)

        def dfs(i, total):
            if i == len(stones):
                return abs(total - (stoneSum - total))
            return min(dfs(i + 1, total), dfs(i + 1, total + stones[i]))

        return dfs(0, 0)
''',
    },
]

CLEAN_VARIANTS = []
