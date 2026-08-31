"""Shared fixture corpus for the enrichment and retrieval evals.

Solutions are canonical (correct, idiomatic) reference implementations - NOT
Aviv's data, which starts empty and would make eval numbers drift week to week.
The 13 feedback-bank problems contribute their verified CANONICAL solutions;
the rest are added here to span patterns the bank cannot cover (trees, graphs,
linked lists, tries, heaps).

`accept` is the ground-truth set for `intended_pattern`. The PRIMARY entry is
dictated by the problem's section in NeetCode's published Blind 75 ordering -
an external taxonomy, not our opinion. Alternates are added ONLY where that
section is coarser than our 26-pattern vocabulary ("Graphs" covers dfs, bfs,
union-find and topological-sort) or where a problem genuinely has two canonical
approaches (Longest Palindromic Substring: expand-around-center or DP). They
are listed explicitly so a reader can disagree with any single one.
"""

import json
from dataclasses import dataclass

from coach import config
from evals.bank.problems import load_all

# NeetCode's Blind 75 section boundaries, by index into coach/curriculum/blind75.json.
NEETCODE_SECTIONS = [
    (0, 8, "Arrays & Hashing"),
    (8, 11, "Two Pointers"),
    (11, 15, "Sliding Window"),
    (15, 16, "Stack"),
    (16, 18, "Binary Search"),
    (18, 24, "Linked List"),
    (24, 35, "Trees"),
    (35, 36, "Heap / Priority Queue"),
    (36, 38, "Backtracking"),
    (38, 41, "Tries"),
    (41, 48, "Graphs"),
    (48, 58, "1-D DP"),
    (58, 60, "2-D DP"),
    (60, 62, "Greedy"),
    (62, 67, "Intervals"),
    (67, 70, "Math & Geometry"),
    (70, 75, "Bit Manipulation"),
]

SECTION_PATTERN = {
    "Arrays & Hashing": "hashmap",
    "Two Pointers": "two-pointers",
    "Sliding Window": "sliding-window",
    "Stack": "stack",
    "Binary Search": "binary-search",
    "Linked List": "linked-list",
    "Trees": "tree",
    "Heap / Priority Queue": "heap",
    "Backtracking": "backtracking",
    "Tries": "trie",
    "Graphs": "graph",
    "1-D DP": "dp-1d",
    "2-D DP": "dp-2d",
    "Greedy": "greedy",
    "Intervals": "intervals",
    "Math & Geometry": "math",
    "Bit Manipulation": "bit-manipulation",
}

# Alternates beyond the section's own pattern. Each is a case where our
# vocabulary is finer than NeetCode's section label, or the problem has two
# textbook solutions.
ALTERNATES = {
    "product-of-array-except-self": ["prefix-sum"],
    "top-k-frequent-elements": ["heap"],
    "longest-consecutive-sequence": [],
    "encode-and-decode-strings": ["design"],
    "best-time-to-buy-and-sell-stock": ["greedy", "dp-1d"],
    "linked-list-cycle": ["two-pointers"],
    "merge-k-sorted-lists": ["heap"],
    "invert-binary-tree": ["dfs"],
    "maximum-depth-of-binary-tree": ["dfs", "bfs"],
    "same-tree": ["dfs"],
    "binary-tree-level-order-traversal": ["bfs"],
    "validate-binary-search-tree": ["dfs"],
    "find-median-from-data-stream": ["design"],
    "word-search": ["dfs"],
    "implement-trie-prefix-tree": ["design"],
    "design-add-and-search-words-data-structure": ["design", "backtracking"],
    "word-search-ii": ["backtracking", "dfs"],
    "number-of-islands": ["dfs", "bfs"],
    "clone-graph": ["dfs", "bfs"],
    "pacific-atlantic-water-flow": ["dfs", "bfs"],
    "course-schedule": ["topological-sort", "dfs"],
    "number-of-connected-components-in-an-undirected-graph": ["union-find", "dfs"],
    "graph-valid-tree": ["union-find", "dfs"],
    "alien-dictionary": ["topological-sort"],
    "coin-change": ["dp-knapsack"],
    "word-break": ["dp-on-strings"],
    "longest-palindromic-substring": ["dp-on-strings", "two-pointers", "dp-2d"],
    "palindromic-substrings": ["dp-on-strings", "two-pointers", "dp-2d"],
    "decode-ways": ["dp-on-strings"],
    "longest-common-subsequence": ["dp-on-strings"],
    "maximum-subarray": ["dp-1d"],
    "jump-game": ["dp-1d"],
    "meeting-rooms-ii": ["heap"],
    "counting-bits": ["dp-1d"],
    "missing-number": ["math"],
    "valid-parentheses": [],
}


def ground_truth() -> dict[str, list[str]]:
    """slug -> acceptable intended_pattern values, from NeetCode's sections."""
    slugs = json.loads((config.PROJECT_ROOT / "coach" / "curriculum" / "blind75.json").read_text())
    truth = {}
    for start, end, section in NEETCODE_SECTIONS:
        for slug in slugs[start:end]:
            truth[slug] = [SECTION_PATTERN[section], *ALTERNATES.get(slug, [])]
    return truth


@dataclass(frozen=True)
class Entry:
    slug: str
    number: int
    title: str
    difficulty: str
    official_tags: str
    code: str
    accept: tuple[str, ...]


# Reference solutions for problems the executable bank cannot cover.
EXTRA_SOLUTIONS = {
    "3sum": '''\
class Solution:
    def threeSum(self, nums):
        nums.sort()
        out = []
        for i in range(len(nums) - 2):
            if i and nums[i] == nums[i - 1]:
                continue
            lo, hi = i + 1, len(nums) - 1
            while lo < hi:
                total = nums[i] + nums[lo] + nums[hi]
                if total < 0:
                    lo += 1
                elif total > 0:
                    hi -= 1
                else:
                    out.append([nums[i], nums[lo], nums[hi]])
                    lo += 1
                    while lo < hi and nums[lo] == nums[lo - 1]:
                        lo += 1
        return out
''',
    "longest-consecutive-sequence": '''\
class Solution:
    def longestConsecutive(self, nums):
        values = set(nums)
        best = 0
        for x in values:
            if x - 1 in values:
                continue
            length = 1
            while x + length in values:
                length += 1
            best = max(best, length)
        return best
''',
    "top-k-frequent-elements": '''\
class Solution:
    def topKFrequent(self, nums, k):
        counts = {}
        for x in nums:
            counts[x] = counts.get(x, 0) + 1
        buckets = [[] for _ in range(len(nums) + 1)]
        for value, count in counts.items():
            buckets[count].append(value)
        out = []
        for count in range(len(buckets) - 1, 0, -1):
            for value in buckets[count]:
                out.append(value)
                if len(out) == k:
                    return out
        return out
''',
    "reverse-linked-list": '''\
class Solution:
    def reverseList(self, head):
        previous = None
        while head:
            head.next, previous, head = previous, head, head.next
        return previous
''',
    "linked-list-cycle": '''\
class Solution:
    def hasCycle(self, head):
        slow = fast = head
        while fast and fast.next:
            slow = slow.next
            fast = fast.next.next
            if slow is fast:
                return True
        return False
''',
    "invert-binary-tree": '''\
class Solution:
    def invertTree(self, root):
        if not root:
            return None
        root.left, root.right = self.invertTree(root.right), self.invertTree(root.left)
        return root
''',
    "binary-tree-level-order-traversal": '''\
from collections import deque


class Solution:
    def levelOrder(self, root):
        if not root:
            return []
        out = []
        queue = deque([root])
        while queue:
            level = []
            for _ in range(len(queue)):
                node = queue.popleft()
                level.append(node.val)
                if node.left:
                    queue.append(node.left)
                if node.right:
                    queue.append(node.right)
            out.append(level)
        return out
''',
    "number-of-islands": '''\
class Solution:
    def numIslands(self, grid):
        if not grid:
            return 0
        rows, cols = len(grid), len(grid[0])

        def sink(r, c):
            if r < 0 or c < 0 or r >= rows or c >= cols or grid[r][c] != "1":
                return
            grid[r][c] = "0"
            sink(r + 1, c)
            sink(r - 1, c)
            sink(r, c + 1)
            sink(r, c - 1)

        count = 0
        for r in range(rows):
            for c in range(cols):
                if grid[r][c] == "1":
                    count += 1
                    sink(r, c)
        return count
''',
    "course-schedule": '''\
from collections import deque


class Solution:
    def canFinish(self, numCourses, prerequisites):
        graph = [[] for _ in range(numCourses)]
        indegree = [0] * numCourses
        for course, need in prerequisites:
            graph[need].append(course)
            indegree[course] += 1
        queue = deque(c for c in range(numCourses) if indegree[c] == 0)
        seen = 0
        while queue:
            node = queue.popleft()
            seen += 1
            for nxt in graph[node]:
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    queue.append(nxt)
        return seen == numCourses
''',
    "combination-sum": '''\
class Solution:
    def combinationSum(self, candidates, target):
        out = []

        def walk(start, left, current):
            if left == 0:
                out.append(current[:])
                return
            for i in range(start, len(candidates)):
                if candidates[i] <= left:
                    current.append(candidates[i])
                    walk(i, left - candidates[i], current)
                    current.pop()

        walk(0, target, [])
        return out
''',
    "implement-trie-prefix-tree": '''\
class Trie:
    def __init__(self):
        self.children = {}
        self.word = False

    def insert(self, word):
        node = self
        for ch in word:
            node = node.children.setdefault(ch, Trie())
        node.word = True

    def search(self, word):
        node = self._walk(word)
        return node is not None and node.word

    def startsWith(self, prefix):
        return self._walk(prefix) is not None

    def _walk(self, text):
        node = self
        for ch in text:
            if ch not in node.children:
                return None
            node = node.children[ch]
        return node
''',
    "unique-paths": '''\
class Solution:
    def uniquePaths(self, m, n):
        row = [1] * n
        for _ in range(m - 1):
            for c in range(1, n):
                row[c] += row[c - 1]
        return row[-1]
''',
    "number-of-1-bits": '''\
class Solution:
    def hammingWeight(self, n):
        count = 0
        while n:
            n &= n - 1
            count += 1
        return count
''',
    "insert-interval": '''\
class Solution:
    def insert(self, intervals, newInterval):
        out = []
        start, end = newInterval
        i = 0
        while i < len(intervals) and intervals[i][1] < start:
            out.append(intervals[i])
            i += 1
        while i < len(intervals) and intervals[i][0] <= end:
            start = min(start, intervals[i][0])
            end = max(end, intervals[i][1])
            i += 1
        out.append([start, end])
        out.extend(intervals[i:])
        return out
''',
    "search-in-rotated-sorted-array": '''\
class Solution:
    def search(self, nums, target):
        lo, hi = 0, len(nums) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            if nums[mid] == target:
                return mid
            if nums[lo] <= nums[mid]:
                if nums[lo] <= target < nums[mid]:
                    hi = mid - 1
                else:
                    lo = mid + 1
            else:
                if nums[mid] < target <= nums[hi]:
                    lo = mid + 1
                else:
                    hi = mid - 1
        return -1
''',
    "counting-bits": '''\
class Solution:
    def countBits(self, n):
        out = [0] * (n + 1)
        for i in range(1, n + 1):
            out[i] = out[i >> 1] + (i & 1)
        return out
''',
}


def load() -> list[Entry]:
    catalog = {p["slug"]: p for p in json.loads(config.CATALOG_PATH.read_text())}
    truth = ground_truth()

    code_by_slug = {p.SLUG: p.CANONICAL for p in load_all()}
    code_by_slug.update(EXTRA_SOLUTIONS)

    entries = []
    for slug, code in sorted(code_by_slug.items()):
        problem = catalog[slug]
        entries.append(
            Entry(
                slug=slug,
                number=problem["number"],
                title=problem["title"],
                difficulty=problem["difficulty"],
                official_tags=json.dumps(problem["tags"]),
                code=code,
                accept=tuple(truth[slug]),
            )
        )
    return entries
