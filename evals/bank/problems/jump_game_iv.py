from collections import deque

from evals.bank.controls import PRELUDE, external_code

NUMBER = 1345
SLUG = "jump-game-iv"
TITLE = "Jump Game IV"
DIFFICULTY = "Hard"
SPLIT = "test"
METHOD = "minJumps"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    (([100, -23, -23, 404, 100, 23, 23, 23, 3, 404],), 3, "general"),
    (([7, 6, 9, 6, 9, 6, 9, 7],), 1, "general"),
    (([6, 1, 9],), 2, "general"),
    (([11, 22, 7, 7, 7, 7, 7, 7, 7, 22, 13],), 3, "general"),
    (([1, 2],), 1, "general"),
    (([7],), 0, "edge"),
]

# Most of the array shares one value, so a search that keeps rescanning that value's
# indices pays for all of them from every one of them.
SCALE = ([7] * 2999 + [8],)
SPACE_SCALE = ([7] * 2999 + [8],)


def reference(arr):
    n = len(arr)
    steps = {0: 0}
    frontier = deque([0])
    while frontier:
        i = frontier.popleft()
        for j in range(n):
            if j not in steps and (abs(i - j) == 1 or (arr[i] == arr[j] and i != j)):
                steps[j] = steps[i] + 1
                frontier.append(j)
    return steps[n - 1]


def valid(arr):
    # 1 <= arr.length <= 5 * 10^4, -10^8 <= arr[i] <= 10^8
    return 1 <= len(arr) <= 5 * 10**4 and all(-10**8 <= x <= 10**8 for x in arr)


def generate(rng):
    return ([rng.randint(0, 3) for _ in range(rng.randint(1, 9))],)


def is_edge(arr):
    return len(arr) == 1


MUTANTS = [
    {
        "id": "never-steps-back",
        "mutation": "weaker-structure",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def minJumps(self, arr: List[int]) -> int:
        n = len(arr)
        graph = collections.defaultdict(list)
        step = 0
        q = collections.deque([0])
        seen = {0}

        for i, a in enumerate(arr):
            graph[a].append(i)

        while q:
            for _ in range(len(q)):
                i = q.popleft()
                if i == n - 1:
                    return step
                u = arr[i]
                if i + 1 < n:
                    graph[u].append(i + 1)
                for v in graph[u]:
                    if v in seen:
                        continue
                    seen.add(v)
                    q.append(v)
                graph[u].clear()
            step += 1
''',
    },
    {
        "id": "start-never-checked",
        "mutation": "missing-guard",
        "intended": "edge-case",
        "code": PRELUDE + '''\
class Solution:
    def minJumps(self, arr: List[int]) -> int:
        n = len(arr)
        d = defaultdict(list)
        for i in reversed(range(n)):
            d[arr[i]].append(i)

        def getUnqueuedNeighbors(i: int) -> List[int]:
            adj = []
            if 0 < i and not seen[i - 1]:
                seen[i - 1] = True
                adj.append(i - 1)
            if i < n - 1 and not seen[i + 1]:
                seen[i + 1] = True
                adj.append(i + 1)
            if arr[i] in d:
                for node in d[arr[i]]:
                    if node != i:
                        adj.append(node)
                        seen[node] = True
                d.pop(arr[i])
            return adj

        seen = [False] * n
        seen[0] = True
        steps, level = 0, deque([0])
        while level:
            steps += 1
            for _ in range(len(level)):
                current = level.popleft()
                for nei in getUnqueuedNeighbors(current):
                    if nei == n - 1:
                        return steps
                    level.append(nei)
''',
    },
    {
        "id": "rescans-equal-values",
        "mutation": "missing-guard",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def minJumps(self, arr: List[int]) -> int:
        n = len(arr)
        if n < 2:
            return 0
        indices = defaultdict(list)
        for i, a in enumerate(arr):
            indices[a].append(i)
        seen = {0}
        q = deque([0])
        steps = 0
        while q:
            steps += 1
            for _ in range(len(q)):
                i = q.popleft()
                for j in [i - 1, i + 1] + indices[arr[i]]:
                    if 0 <= j < n and j not in seen:
                        if j == n - 1:
                            return steps
                        seen.add(j)
                        q.append(j)
''',
    },
]

CLEAN_VARIANTS = []
