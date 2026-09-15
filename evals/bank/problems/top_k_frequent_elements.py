from evals.bank.controls import PRELUDE, external_code

NUMBER = 347
SLUG = "top-k-frequent-elements"
TITLE = "Top K Frequent Elements"
DIFFICULTY = "Medium"
SPLIT = "test"
METHOD = "topKFrequent"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    (([1, 1, 1, 2, 2, 3], 2), [1, 2], "general"),
    (([4, 4, -1, -1, -1, 2], 1), [-1], "general"),
    (([5, 3, 5, 3, 5, 7, 7, 7, 7], 2), [5, 7], "general"),
    (([1], 1), [1], "edge"),
    (([1, 2], 2), [1, 2], "edge"),
]

SCALE = (list(range(5000)) + [7, 7, 7], 1)
SPACE_SCALE = (list(range(100_000)) + [7], 1)


def normalize(elements):
    """LeetCode accepts the k elements in any order."""
    return sorted(elements)


def reference(nums, k):
    counts = {}
    for x in nums:
        counts[x] = counts.get(x, 0) + 1
    return sorted(counts, key=lambda x: -counts[x])[:k]


def generate(rng):
    # constraints: 1 <= nums.length <= 10^5, k is between 1 and the number of distinct
    # values, and the answer is unique
    while True:
        nums = [rng.randint(-3, 3) for _ in range(rng.randint(1, 12))]
        counts = sorted((nums.count(x) for x in set(nums)), reverse=True)
        k = rng.randint(1, len(counts))
        if k == len(counts) or counts[k - 1] != counts[k]:
            return (nums, k)


MUTANTS = [
    {
        "id": "least-frequent-first",
        "mutation": "wrong-operator",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def topKFrequent(self, nums: List[int], k: int) -> List[int]:
        count = {}
        freq = [[] for i in range(len(nums) + 1)]

        for n in nums:
            count[n] = 1 + count.get(n, 0)
        for n, c in count.items():
            freq[c].append(n)

        res = []
        for i in range(1, len(freq)):
            res += freq[i]
            if len(res) == k:
                return res
''',
    },
    {
        "id": "counts-with-a-set",
        "mutation": "weaker-structure",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def topKFrequent(self, nums: List[int], k: int) -> List[int]:
        count = {}
        freq = [[] for i in range(len(nums) + 1)]

        for n in nums:
            count[n] = 1
        for n, c in count.items():
            freq[c].append(n)

        res = []
        for i in range(len(freq) - 1, 0, -1):
            res += freq[i]
            if len(res) == k:
                return res
''',
    },
    {
        "id": "count-each-value-again",
        "mutation": "brute-force",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def topKFrequent(self, nums: List[int], k: int) -> List[int]:
        unique = list(set(nums))
        unique.sort(key=lambda n: nums.count(n), reverse=True)
        return unique[:k]
''',
    },
]

CLEAN_VARIANTS = []
