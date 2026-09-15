from evals.bank.controls import PRELUDE, external_code

NUMBER = 1851
SLUG = "minimum-interval-to-include-each-query"
TITLE = "Minimum Interval to Include Each Query"
DIFFICULTY = "Hard"
SPLIT = "test"
METHOD = "minInterval"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    (([[1, 4], [2, 4], [3, 6], [4, 4]], [2, 3, 4, 5]), [3, 3, 1, 4], "general"),
    (([[2, 3], [2, 5], [1, 8], [20, 25]], [2, 19, 5, 22]), [2, -1, 4, 6], "general"),
    (([[1, 3], [1, 3]], [3, 3]), [3, 3], "general"),
    (([[1, 1]], [1]), [1], "edge"),
    (([[5, 5]], [4]), [-1], "edge"),
]

SCALE = ([[i, i + i % 50] for i in range(1, 2001)], [(i * 7919) % 2050 + 1 for i in range(2000)])
SPACE_SCALE = ([[i, i + i % 50] for i in range(1, 100_001)], [(i * 7919) % 100_050 + 1 for i in range(100_000)])


def reference(intervals, queries):
    return [min((right - left + 1 for left, right in intervals if left <= q <= right), default=-1)
            for q in queries]


def generate(rng):
    # constraints: 1 <= intervals.length, queries.length <= 10^5, 1 <= left <= right <= 10^7,
    # 1 <= queries[j] <= 10^7
    intervals = []
    for _ in range(rng.randint(1, 6)):
        left = rng.randint(1, 10)
        intervals.append([left, left + rng.randint(0, 5)])
    return (intervals, [rng.randint(1, 15) for _ in range(rng.randint(1, 6))])


MUTANTS = [
    {
        "id": "drops-intervals-ending-at-the-query",
        "mutation": "off-by-one",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def minInterval(self, intervals: List[List[int]], queries: List[int]) -> List[int]:
        intervals.sort()
        minHeap = []
        res = {}
        i = 0
        for q in sorted(queries):
            while i < len(intervals) and intervals[i][0] <= q:
                l, r = intervals[i]
                heapq.heappush(minHeap, (r - l + 1, r))
                i += 1

            while minHeap and minHeap[0][1] <= q:
                heapq.heappop(minHeap)
            res[q] = minHeap[0][0] if minHeap else -1
        return [res[q] for q in queries]
''',
    },
    {
        "id": "answers-in-sorted-order",
        "mutation": "missing-precondition",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def minInterval(self, intervals: List[List[int]], queries: List[int]) -> List[int]:
        intervals.sort()
        minHeap = []
        res = {}
        i = 0
        for q in sorted(queries):
            while i < len(intervals) and intervals[i][0] <= q:
                l, r = intervals[i]
                heapq.heappush(minHeap, (r - l + 1, r))
                i += 1

            while minHeap and minHeap[0][1] < q:
                heapq.heappop(minHeap)
            res[q] = minHeap[0][0] if minHeap else -1
        return [res[q] for q in sorted(queries)]
''',
    },
    {
        "id": "scan-every-interval-per-query",
        "mutation": "brute-force",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def minInterval(self, intervals: List[List[int]], queries: List[int]) -> List[int]:
        res = []
        for q in queries:
            best = -1
            for l, r in intervals:
                if l <= q <= r and (best == -1 or r - l + 1 < best):
                    best = r - l + 1
            res.append(best)
        return res
''',
    },
]

CLEAN_VARIANTS = []
