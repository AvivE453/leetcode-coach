NUMBER = 56
SLUG = "merge-intervals"
TITLE = "Merge Intervals"
DIFFICULTY = "Medium"

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
