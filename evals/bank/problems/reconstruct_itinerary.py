from evals.bank.controls import PRELUDE, external_code

NUMBER = 332
SLUG = "reconstruct-itinerary"
TITLE = "Reconstruct Itinerary"
DIFFICULTY = "Hard"
SPLIT = "test"
METHOD = "findItinerary"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    (([["MUC", "LHR"], ["JFK", "MUC"], ["SFO", "SJC"], ["LHR", "SFO"]],),
     ["JFK", "MUC", "LHR", "SFO", "SJC"], "general"),
    (([["JFK", "SFO"], ["JFK", "ATL"], ["SFO", "ATL"], ["ATL", "JFK"], ["ATL", "SFO"]],),
     ["JFK", "ATL", "JFK", "SFO", "ATL", "SFO"], "general"),
    (([["JFK", "KUL"], ["JFK", "NRT"], ["NRT", "JFK"]],), ["JFK", "NRT", "JFK", "KUL"], "general"),
    (([["JFK", "AAA"]],), ["JFK", "AAA"], "edge"),
]


def airport(i):
    return "B" + chr(65 + i // 26) + chr(65 + i % 26)


SCALE = ([["JFK", airport(0)]] + [[airport(i), airport(i + 1)] for i in range(299)],)
SPACE_SCALE = ([["JFK", airport(0)]] + [[airport(i), airport(i + 1)] for i in range(299)],)


def reference(tickets):
    tickets = sorted(tickets)
    used = [False] * len(tickets)
    route = ["JFK"]

    def extend():
        if len(route) == len(tickets) + 1:
            return True
        for i, (source, destination) in enumerate(tickets):
            if not used[i] and source == route[-1]:
                used[i] = True
                route.append(destination)
                if extend():
                    return True
                route.pop()
                used[i] = False
        return False

    extend()
    return route


def generate(rng):
    # constraints: 1 <= tickets.length <= 300, from != to, and a valid itinerary from JFK exists
    airports = ["JFK", "ATL", "SFO", "LAX"]
    route = ["JFK"]
    for _ in range(rng.randint(1, 6)):
        route.append(rng.choice([code for code in airports if code != route[-1]]))
    tickets = [[route[i], route[i + 1]] for i in range(len(route) - 1)]
    rng.shuffle(tickets)
    return (tickets,)


MUTANTS = [
    {
        "id": "smallest-destination-without-backtracking",
        "mutation": "greedy-substitution",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def findItinerary(self, tickets: List[List[str]]) -> List[str]:
        adj = {}
        for src, dst in sorted(tickets):
            adj.setdefault(src, []).append(dst)
        res = ["JFK"]
        while adj.get(res[-1]):
            res.append(adj[res[-1]].pop(0))
        return res
''',
    },
    {
        "id": "destinations-left-unsorted",
        "mutation": "missing-precondition",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def findItinerary(self, tickets: List[List[str]]) -> List[str]:
        adj = {src: [] for src, dst in tickets}
        res = []

        for src, dst in tickets:
            adj[src].append(dst)

        def dfs(adj, src):
            if src in adj:
                destinations = adj[src][:]
                while destinations:
                    dest = destinations[0]
                    adj[src].pop(0)
                    dfs(adj, dest)
                    destinations = adj[src][:]
            res.append(src)

        dfs(adj, "JFK")
        res.reverse()

        if len(res) != len(tickets) + 1:
            return []

        return res
''',
    },
]

CLEAN_VARIANTS = []
