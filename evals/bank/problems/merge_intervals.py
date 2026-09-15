NUMBER = 56
SLUG = "merge-intervals"
TITLE = "Merge Intervals"
DIFFICULTY = "Medium"
SPLIT = "dev"
METHOD = "merge"

CANONICAL = '''\
class Solution:
    def merge(self, intervals):
        merged = []
        for start, end in sorted(intervals):
            if merged and start <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end])
        return merged
'''

TESTS = [
    (([[1, 3], [2, 6], [8, 10], [15, 18]],), [[1, 6], [8, 10], [15, 18]], "general"),
    (([[1, 4], [4, 5]],), [[1, 5]], "general"),
    (([[2, 6], [1, 3]],), [[1, 6]], "general"),
    (([[1, 4], [2, 3]],), [[1, 4]], "general"),
    # constraints: 1 <= intervals.length
    (([[1, 4]],), [[1, 4]], "edge"),
]

SCALE = ([[i, i + 1] for i in range(0, 6000, 2)],)
SPACE_SCALE = ([[i, i + 1] for i in range(0, 20_000, 2)],)


def normalize(merged):
    """LeetCode accepts the merged intervals in any order, as lists or tuples."""
    return sorted(list(interval) for interval in merged)


def reference(intervals):
    merged = [list(interval) for interval in intervals]
    changed = True
    while changed:
        changed = False
        for a in range(len(merged)):
            for b in range(a + 1, len(merged)):
                if merged[a][0] <= merged[b][1] and merged[b][0] <= merged[a][1]:
                    merged[a] = [min(merged[a][0], merged[b][0]), max(merged[a][1], merged[b][1])]
                    del merged[b]
                    changed = True
                    break
            if changed:
                break
    return sorted(merged)


def generate(rng):
    # constraints: 1 <= intervals.length <= 10^4, 0 <= start <= end <= 10^4
    intervals = []
    for _ in range(rng.randint(1, 8)):
        start = rng.randint(0, 12)
        intervals.append([start, start + rng.randint(0, 5)])
    return (intervals,)

MUTANTS = [
    {
        "id": "assumes-nonempty",
        "mutation": "missing-guard",
        "intended": "edge-case",
        "code": '''\
class Solution:
    def merge(self, intervals):
        ordered = sorted(intervals)
        merged = [ordered[0]]
        for start, end in ordered[1:]:
            if start <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end])
        return merged
''',
    },
    {
        "id": "no-sort",
        "mutation": "missing-precondition",
        "intended": "bug",
        "code": '''\
class Solution:
    def merge(self, intervals):
        merged = []
        for start, end in intervals:
            if merged and start <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end])
        return merged
''',
    },
    {
        "id": "strict-overlap",
        "mutation": "wrong-operator",
        "intended": "bug",
        "code": '''\
class Solution:
    def merge(self, intervals):
        merged = []
        for start, end in sorted(intervals):
            if merged and start < merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end])
        return merged
''',
    },
    {
        "id": "clobber-end",
        "mutation": "missing-guard",
        "intended": "bug",
        "code": '''\
class Solution:
    def merge(self, intervals):
        merged = []
        for start, end in sorted(intervals):
            if merged and start <= merged[-1][1]:
                merged[-1][1] = end
            else:
                merged.append([start, end])
        return merged
''',
    },
]

CLEAN_VARIANTS = [
    {
        "id": "start-key-sort",
        "control": "representative",
        "code": '''\
class Solution:
    def merge(self, intervals):
        merged = []
        for start, end in sorted(intervals, key=lambda interval: interval[0]):
            if not merged or merged[-1][1] < start:
                merged.append([start, end])
            else:
                merged[-1][1] = max(merged[-1][1], end)
        return merged
''',
    },
    {
        "id": "seed-with-first-interval",
        "control": "regression",
        "probes": "flagging an input the constraints exclude (1 <= intervals.length)",
        "code": '''\
class Solution:
    def merge(self, intervals):
        ordered = sorted(intervals)
        merged = [list(ordered[0])]
        for i in range(1, len(ordered)):
            start, end = ordered[i]
            if start <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end])
        return merged
''',
    },
]
