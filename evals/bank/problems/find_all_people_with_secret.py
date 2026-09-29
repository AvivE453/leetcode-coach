from evals.bank.controls import PRELUDE, external_code

NUMBER = 2092
SLUG = "find-all-people-with-secret"
TITLE = "Find All People With Secret"
DIFFICULTY = "Hard"
SPLIT = "test"
METHOD = "findAllPeople"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    ((6, [[1, 2, 5], [2, 3, 8], [1, 5, 10]], 1), [0, 1, 2, 3, 5], "general"),
    ((4, [[3, 1, 3], [1, 2, 2], [0, 3, 3]], 3), [0, 1, 3], "general"),
    ((5, [[3, 4, 2], [1, 2, 1], [2, 3, 1]], 1), [0, 1, 2, 3, 4], "general"),
    ((4, [[1, 2, 2], [2, 3, 1]], 1), [0, 1, 2], "general"),
    ((5, [[1, 4, 3], [0, 4, 3]], 3), [0, 1, 3, 4], "general"),
    ((5, [[3, 4, 1], [2, 3, 1], [1, 2, 1]], 1), [0, 1, 2, 3, 4], "general"),
    ((2, [[0, 1, 1]], 1), [0, 1], "edge"),
]

# One time frame, and a chain whose meetings are listed from the far end, so the secret
# crosses one meeting per pass over the list.
CHAIN = [[i, i + 1, 1] for i in reversed(range(1, 1999))]
SCALE = (2000, CHAIN, 1)
SPACE_SCALE = (2000, CHAIN, 1)


def reference(n, meetings, firstPerson):
    knows = {0, firstPerson}
    for time in sorted({t for _, _, t in meetings}):
        now = [(x, y) for x, y, t in meetings if t == time]
        spread = True
        while spread:
            spread = False
            for x, y in now:
                if (x in knows) != (y in knows):
                    knows |= {x, y}
                    spread = True
    return list(knows)


def normalize(people):
    """LeetCode accepts the people in any order."""
    return sorted(people)


def valid(n, meetings, firstPerson):
    # 2 <= n <= 10^5, 1 <= meetings.length <= 10^5, meetings[i] = [x, y, time],
    # 0 <= x, y < n, x != y, 1 <= time <= 10^5, 1 <= firstPerson < n
    return (2 <= n <= 10**5 and 1 <= len(meetings) <= 10**5
            and all(len(m) == 3 and 0 <= m[0] < n and 0 <= m[1] < n and m[0] != m[1] and 1 <= m[2] <= 10**5
                    for m in meetings)
            and 1 <= firstPerson < n)


def generate(rng):
    n = rng.randint(2, 6)
    meetings = [[*rng.sample(range(n), 2), rng.randint(1, 4)] for _ in range(rng.randint(1, 6))]
    return (n, meetings, rng.randint(1, n - 1))


MUTANTS = [
    {
        "id": "meetings-in-listed-order",
        "mutation": "missing-precondition",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def findAllPeople(self, n: int, meetings: List[List[int]], firstPerson: int) -> List[int]:
        secrets = set([0, firstPerson])
        time_map = {}

        for src, dst, t in meetings:
            if t not in time_map:
                time_map[t] = defaultdict(list)
            time_map[t][src].append(dst)
            time_map[t][dst].append(src)

        def dfs(src, adj):
            if src in visit:
                return
            visit.add(src)
            secrets.add(src)
            for nei in adj[src]:
                dfs(nei, adj)

        for t in time_map:
            visit = set()
            for src in time_map[t]:
                if src in secrets:
                    dfs(src, time_map[t])
        return list(secrets)
''',
    },
    {
        "id": "one-pass-per-time-frame",
        "mutation": "greedy-substitution",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def findAllPeople(self, n: int, meetings: List[List[int]], firstPerson: int) -> List[int]:
        knows = {0, firstPerson}
        for x, y, t in sorted(meetings, key=lambda m: m[2]):
            if x in knows or y in knows:
                knows.add(x)
                knows.add(y)
        return list(knows)
''',
    },
    {
        "id": "rescans-until-nothing-spreads",
        "mutation": "brute-force",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def findAllPeople(self, n: int, meetings: List[List[int]], firstPerson: int) -> List[int]:
        knows = {0, firstPerson}
        by_time = defaultdict(list)
        for x, y, t in meetings:
            by_time[t].append((x, y))
        for t in sorted(by_time):
            changed = True
            while changed:
                changed = False
                for x, y in by_time[t]:
                    if (x in knows) != (y in knows):
                        knows.add(x)
                        knows.add(y)
                        changed = True
        return list(knows)
''',
    },
]

CLEAN_VARIANTS = []
