from evals.bank.controls import PRELUDE, external_code

NUMBER = 57
SLUG = "insert-interval"
TITLE = "Insert Interval"
DIFFICULTY = "Medium"
SPLIT = "test"
METHOD = "insert"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    (([[1, 3], [6, 9]], [2, 5]), [[1, 5], [6, 9]], "general"),
    (([[1, 2], [3, 5], [6, 7], [8, 10], [12, 16]], [4, 8]), [[1, 2], [3, 10], [12, 16]], "general"),
    (([[1, 5]], [6, 8]), [[1, 5], [6, 8]], "general"),
    (([[3, 5]], [1, 2]), [[1, 2], [3, 5]], "general"),
    (([[3, 5]], [1, 3]), [[1, 5]], "general"),
    (([[1, 5]], [5, 7]), [[1, 7]], "general"),
    (([[1, 5]], [2, 3]), [[1, 5]], "general"),
    (([], [5, 7]), [[5, 7]], "edge"),
]

SCALE = ([[2 * i, 2 * i + 1] for i in range(2000)], [5000, 5001])
SPACE_SCALE = ([[2 * i, 2 * i + 1] for i in range(10_000)], [30_000, 30_001])


def reference(intervals, newInterval):
    merged = []
    for start, end in sorted(intervals + [newInterval]):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged


def generate(rng):
    # constraints: 0 <= intervals.length <= 10^4, sorted by start and non-overlapping,
    # 0 <= start <= end <= 10^5
    points = sorted(rng.sample(range(30), 2 * rng.randint(0, 4)))
    intervals = [[points[i], points[i + 1]] for i in range(0, len(points), 2)]
    start = rng.randint(0, 30)
    return (intervals, [start, start + rng.randint(0, 6)])


def is_edge(intervals, newInterval):
    return not intervals


MUTANTS = [
    {
        "id": "touching-does-not-merge",
        "mutation": "wrong-operator",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def insert(
        self, intervals: List[List[int]], newInterval: List[int]
    ) -> List[List[int]]:
        res = []

        for i in range(len(intervals)):
            if newInterval[1] <= intervals[i][0]:
                res.append(newInterval)
                return res + intervals[i:]
            elif newInterval[0] > intervals[i][1]:
                res.append(intervals[i])
            else:
                newInterval = [
                    min(newInterval[0], intervals[i][0]),
                    max(newInterval[1], intervals[i][1]),
                ]
        res.append(newInterval)
        return res
''',
    },
    {
        "id": "keeps-the-new-start",
        "mutation": "missing-guard",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def insert(
        self, intervals: List[List[int]], newInterval: List[int]
    ) -> List[List[int]]:
        res = []

        for i in range(len(intervals)):
            if newInterval[1] < intervals[i][0]:
                res.append(newInterval)
                return res + intervals[i:]
            elif newInterval[0] > intervals[i][1]:
                res.append(intervals[i])
            else:
                newInterval = [
                    newInterval[0],
                    max(newInterval[1], intervals[i][1]),
                ]
        res.append(newInterval)
        return res
''',
    },
    {
        "id": "fast-path-before-any-guard",
        "mutation": "missing-guard",
        "intended": "edge-case",
        "code": PRELUDE + '''\
class Solution:
    def insert(
        self, intervals: List[List[int]], newInterval: List[int]
    ) -> List[List[int]]:
        if newInterval[1] < intervals[0][0]:
            return [newInterval] + intervals
        res = []

        for i in range(len(intervals)):
            if newInterval[1] < intervals[i][0]:
                res.append(newInterval)
                return res + intervals[i:]
            elif newInterval[0] > intervals[i][1]:
                res.append(intervals[i])
            else:
                newInterval = [
                    min(newInterval[0], intervals[i][0]),
                    max(newInterval[1], intervals[i][1]),
                ]
        res.append(newInterval)
        return res
''',
    },
    {
        "id": "merge-pairs-until-stable",
        "mutation": "brute-force",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def insert(
        self, intervals: List[List[int]], newInterval: List[int]
    ) -> List[List[int]]:
        res = [list(interval) for interval in intervals] + [list(newInterval)]
        merged = True
        while merged:
            merged = False
            for a in range(len(res)):
                for b in range(a + 1, len(res)):
                    if res[a][0] <= res[b][1] and res[b][0] <= res[a][1]:
                        res[a] = [min(res[a][0], res[b][0]), max(res[a][1], res[b][1])]
                        del res[b]
                        merged = True
                        break
                if merged:
                    break
        return sorted(res)
''',
    },
]

CLEAN_VARIANTS = []
