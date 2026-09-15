from evals.bank.controls import PRELUDE, external_code

NUMBER = 55
SLUG = "jump-game"
TITLE = "Jump Game"
DIFFICULTY = "Medium"
SPLIT = "dev"
METHOD = "canJump"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    (([2, 3, 1, 1, 4],), True, "general"),
    (([3, 2, 1, 0, 4],), False, "general"),
    (([1, 0, 1],), False, "general"),
    (([2, 0, 0],), True, "general"),
    (([0],), True, "edge"),
    (([0, 1],), False, "edge"),
]

SCALE = ([3000] * 3000,)
SPACE_SCALE = ([1] * 10_000,)


def reference(nums):
    reachable = [False] * len(nums)
    reachable[0] = True
    for i, jump in enumerate(nums):
        if reachable[i]:
            for j in range(i + 1, min(len(nums), i + jump + 1)):
                reachable[j] = True
    return reachable[-1]


def generate(rng):
    # constraints: 1 <= nums.length <= 10^4, 0 <= nums[i] <= 10^5
    return ([rng.randint(0, 3) for _ in range(rng.randint(1, 8))],)


MUTANTS = [
    {
        "id": "goal-past-the-last-index",
        "mutation": "off-by-one",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def canJump(self, nums: List[int]) -> bool:
        goal = len(nums)

        for i in range(len(nums) - 2, -1, -1):
            if i + nums[i] >= goal:
                goal = i
        return goal == 0
''',
    },
    {
        "id": "landing-exactly-does-not-count",
        "mutation": "wrong-operator",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def canJump(self, nums: List[int]) -> bool:
        goal = len(nums) - 1

        for i in range(len(nums) - 2, -1, -1):
            if i + nums[i] > goal:
                goal = i
        return goal == 0
''',
    },
    {
        "id": "mark-every-reachable-index",
        "mutation": "brute-force",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def canJump(self, nums: List[int]) -> bool:
        reachable = [False] * len(nums)
        reachable[0] = True
        for i in range(len(nums)):
            if reachable[i]:
                for j in range(i + 1, min(len(nums), i + nums[i] + 1)):
                    reachable[j] = True
        return reachable[-1]
''',
    },
]

CLEAN_VARIANTS = []
