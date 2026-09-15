from evals.bank.controls import PRELUDE, external_code

NUMBER = 207
SLUG = "course-schedule"
TITLE = "Course Schedule"
DIFFICULTY = "Medium"
SPLIT = "dev"
METHOD = "canFinish"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    ((2, [[1, 0]]), True, "general"),
    ((2, [[1, 0], [0, 1]]), False, "general"),
    ((3, [[0, 1], [1, 2], [2, 0]]), False, "general"),
    ((4, [[1, 0], [2, 1], [3, 2]]), True, "general"),
    ((3, [[1, 0], [2, 0]]), True, "general"),
    ((1, []), True, "edge"),
]


def layered(layers):
    """Two courses per layer, each needing both courses of the layer below: 2^layers paths."""
    return [[course, below] for layer in range(1, layers) for course in (2 * layer, 2 * layer + 1)
            for below in (2 * layer - 2, 2 * layer - 1)]


SCALE = (36, layered(18))
SPACE_SCALE = (2000, [[i + 1, i] for i in range(1999)])


def reference(numCourses, prerequisites):
    remaining = set(range(numCourses))
    progress = True
    while progress:
        progress = False
        for course in list(remaining):
            if all(pre not in remaining for needed, pre in prerequisites if needed == course):
                remaining.discard(course)
                progress = True
    return not remaining


def generate(rng):
    # constraints: 1 <= numCourses <= 2000, 0 <= prerequisites.length <= 5000, unique pairs
    courses = rng.randint(1, 6)
    pairs = {(rng.randrange(courses), rng.randrange(courses)) for _ in range(rng.randint(0, 6))}
    return (courses, [[a, b] for a, b in sorted(pairs) if a != b])


MUTANTS = [
    {
        "id": "courses-stay-marked-as-visiting",
        "mutation": "missing-guard",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def canFinish(self, numCourses: int, prerequisites: List[List[int]]) -> bool:
        # dfs
        preMap = {i: [] for i in range(numCourses)}

        # map each course to : prereq list
        for crs, pre in prerequisites:
            preMap[crs].append(pre)

        visiting = set()

        def dfs(crs):
            if crs in visiting:
                return False
            if preMap[crs] == []:
                return True

            visiting.add(crs)
            for pre in preMap[crs]:
                if not dfs(pre):
                    return False
            preMap[crs] = []
            return True

        for c in range(numCourses):
            if not dfs(c):
                return False
        return True
''',
    },
    {
        "id": "finished-courses-are-rechecked",
        "mutation": "missing-precondition",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def canFinish(self, numCourses: int, prerequisites: List[List[int]]) -> bool:
        # dfs
        preMap = {i: [] for i in range(numCourses)}

        # map each course to : prereq list
        for crs, pre in prerequisites:
            preMap[crs].append(pre)

        visiting = set()

        def dfs(crs):
            if crs in visiting:
                return False
            if preMap[crs] == []:
                return True

            visiting.add(crs)
            for pre in preMap[crs]:
                if not dfs(pre):
                    return False
            visiting.remove(crs)
            return True

        for c in range(numCourses):
            if not dfs(c):
                return False
        return True
''',
    },
]

CLEAN_VARIANTS = []
