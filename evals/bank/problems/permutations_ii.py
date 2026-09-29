from itertools import permutations

from evals.bank.controls import PRELUDE, external_code

NUMBER = 47
SLUG = "permutations-ii"
TITLE = "Permutations II"
DIFFICULTY = "Medium"
SPLIT = "test"
METHOD = "permuteUnique"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    (([1, 1, 2],), [[1, 1, 2], [1, 2, 1], [2, 1, 1]], "general"),
    (([1, 2, 3],), [[1, 2, 3], [1, 3, 2], [2, 1, 3], [2, 3, 1], [3, 1, 2], [3, 2, 1]], "general"),
    (([1, 2, 1],), [[1, 1, 2], [1, 2, 1], [2, 1, 1]], "general"),
    (([2, 2, 2],), [[2, 2, 2]], "general"),
    (([-1, 0],), [[-1, 0], [0, -1]], "general"),
    (([1],), [[1]], "edge"),
]

# At most 8 numbers, so no way of listing the permutations is slower in a way that
# matters, and the problem has no complexity mutant.
SCALE = ([1, 1, 2, 2, 3, 3, 4, 4],)
SPACE_SCALE = ([1, 2, 3, 4, 5, 6, 7, 8],)


def reference(nums):
    return [list(p) for p in set(permutations(nums))]


def normalize(perms):
    """LeetCode accepts the permutations in any order, but each exactly once."""
    return sorted(list(p) for p in perms)


def valid(nums):
    # 1 <= nums.length <= 8, -10 <= nums[i] <= 10
    return 1 <= len(nums) <= 8 and all(-10 <= x <= 10 for x in nums)


def generate(rng):
    return ([rng.randint(-2, 2) for _ in range(rng.randint(1, 6))],)


MUTANTS = [
    {
        "id": "skips-duplicates-without-sorting",
        "mutation": "missing-precondition",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def permuteUnique(self, nums: List[int]) -> List[List[int]]:
        ans = []
        used = [False] * len(nums)

        def dfs(path):
            if len(path) == len(nums):
                ans.append(path.copy())
                return

            for i, num in enumerate(nums):
                if used[i]:
                    continue
                if i > 0 and nums[i] == nums[i - 1] and not used[i - 1]:
                    continue
                used[i] = True
                path.append(num)
                dfs(path)
                path.pop()
                used[i] = False

        dfs([])
        return ans
''',
    },
    {
        "id": "branches-on-every-copy",
        "mutation": "weaker-structure",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def permuteUnique(self, nums: List[int]) -> List[List[int]]:
        result = []
        counter = collections.Counter(nums)

        def backtrack(perm):
            if len(perm) == len(nums):
                result.append(perm.copy())

            for n in nums:
                if counter[n] == 0:
                    continue
                perm.append(n)
                counter[n] -= 1
                backtrack(perm)
                perm.pop()
                counter[n] += 1

        backtrack([])

        return result
''',
    },
]

CLEAN_VARIANTS = []
