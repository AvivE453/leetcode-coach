from evals.bank.controls import PRELUDE, external_code

NUMBER = 435
SLUG = "non-overlapping-intervals"
TITLE = "Non-overlapping Intervals"
DIFFICULTY = "Medium"
SPLIT = "test"
METHOD = "eraseOverlapIntervals"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    (([[1, 2], [2, 3], [3, 4], [1, 3]],), 1, "general"),
    (([[1, 2], [1, 2], [1, 2]],), 2, "general"),
    (([[1, 2], [2, 3]],), 0, "general"),
    (([[1, 100], [11, 22], [1, 11], [2, 12]],), 2, "general"),
    (([[0, 5]],), 0, "edge"),
]

SCALE = ([[i, i + 2] for i in range(2000)],)
SPACE_SCALE = ([[i, i + 2] for i in range(100_000)],)


def reference(intervals):
    n = len(intervals)
    most = 0
    for chosen in range(1 << n):
        picked = sorted(intervals[i] for i in range(n) if chosen >> i & 1)
        if all(picked[i][1] <= picked[i + 1][0] for i in range(len(picked) - 1)):
            most = max(most, len(picked))
    return n - most


def generate(rng):
    # constraints: 1 <= intervals.length <= 10^5, -5 * 10^4 <= start < end <= 5 * 10^4
    intervals = []
    for _ in range(rng.randint(1, 8)):
        start = rng.randint(0, 10)
        intervals.append([start, start + rng.randint(1, 4)])
    return (intervals,)


MUTANTS = [
    {
        "id": "keeps-the-later-end",
        "mutation": "greedy-substitution",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def eraseOverlapIntervals(self, intervals: List[List[int]]) -> int:
        intervals.sort()
        res = 0
        prevEnd = intervals[0][1]
        for start, end in intervals[1:]:
            if start >= prevEnd:
                prevEnd = end
            else:
                res += 1
                prevEnd = max(end, prevEnd)
        return res
''',
    },
    {
        "id": "touching-counts-as-overlap",
        "mutation": "wrong-operator",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def eraseOverlapIntervals(self, intervals: List[List[int]]) -> int:
        intervals.sort()
        res = 0
        prevEnd = intervals[0][1]
        for start, end in intervals[1:]:
            if start > prevEnd:
                prevEnd = end
            else:
                res += 1
                prevEnd = min(end, prevEnd)
        return res
''',
    },
    {
        "id": "longest-chain-by-dp",
        "mutation": "brute-force",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def eraseOverlapIntervals(self, intervals: List[List[int]]) -> int:
        intervals.sort()
        keep = [1] * len(intervals)
        for i in range(len(intervals)):
            for j in range(i):
                if intervals[j][1] <= intervals[i][0]:
                    keep[i] = max(keep[i], keep[j] + 1)
        return len(intervals) - max(keep)
''',
    },
]

CLEAN_VARIANTS = []
