from evals.bank.controls import PRELUDE, external_code

NUMBER = 2306
SLUG = "naming-a-company"
TITLE = "Naming a Company"
DIFFICULTY = "Hard"
SPLIT = "test"
METHOD = "distinctNames"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    ((["coffee", "donuts", "time", "toffee"],), 6, "general"),
    ((["lack", "back"],), 0, "general"),
    ((["aaa", "baa", "caa", "bbb", "cbb", "dbb"],), 2, "general"),
    ((["abc", "abd", "bbc"],), 0, "general"),
    ((["ab", "cd", "ef"],), 6, "general"),
    ((["ab", "cd"],), 2, "edge"),
    ((["a", "b"],), 0, "edge"),
]

def spelled(number):
    """A number written in letters, one per base-26 digit, so every number gets its own suffix."""
    letters = ""
    while True:
        number, digit = divmod(number, 26)
        letters += chr(ord("a") + digit)
        if not number:
            return letters


SCALE = ([chr(ord("a") + i % 26) + spelled(i // 26) for i in range(3000)],)
SPACE_SCALE = ([chr(ord("a") + i % 26) + spelled(i // 26) for i in range(5 * 10**4)],)


def reference(ideas):
    names = set(ideas)
    return sum(b[0] + a[1:] not in names and a[0] + b[1:] not in names
               for a in ideas for b in ideas if a != b)


def valid(ideas):
    # 2 <= ideas.length <= 5 * 10^4, 1 <= ideas[i].length <= 10, lowercase, all unique
    return (2 <= len(ideas) <= 5 * 10**4 and len(set(ideas)) == len(ideas)
            and all(1 <= len(idea) <= 10 and idea.isascii() and idea.isalpha() and idea.islower()
                    for idea in ideas))


def generate(rng):
    ideas = set()
    size = rng.randint(2, 8)
    while len(ideas) < size:
        ideas.add("".join(rng.choice("abc") for _ in range(rng.randint(1, 3))))
    # Sorted: a set's order changes between runs, and the oracle must judge the same inputs.
    return (sorted(ideas),)


def is_edge(ideas):
    return len(ideas) == 2


MUTANTS = [
    {
        "id": "counts-each-pair-once",
        "mutation": "wrong-operator",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def distinctNames(self, ideas: List[str]) -> int:
        ans = 0
        suffixes = [set() for _ in range(26)]

        for idea in ideas:
            suffixes[ord(idea[0]) - ord('a')].add(idea[1:])

        for i, j in itertools.combinations(range(26), 2):
            count = len(suffixes[i] & suffixes[j])
            ans += (len(suffixes[i]) - count) * (len(suffixes[j]) - count)

        return ans
''',
    },
    {
        "id": "shared-suffixes-not-removed",
        "mutation": "missing-guard",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def distinctNames(self, ideas: List[str]) -> int:
        ans = 0
        suffixes = [set() for _ in range(26)]

        for idea in ideas:
            suffixes[ord(idea[0]) - ord('a')].add(idea[1:])

        for i, j in itertools.combinations(range(26), 2):
            ans += 2 * len(suffixes[i]) * len(suffixes[j])

        return ans
''',
    },
    {
        "id": "tries-every-pair",
        "mutation": "brute-force",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def distinctNames(self, ideas: List[str]) -> int:
        names = set(ideas)
        count = 0
        for a in ideas:
            for b in ideas:
                if a[0] != b[0] and b[0] + a[1:] not in names and a[0] + b[1:] not in names:
                    count += 1
        return count
''',
    },
]

CLEAN_VARIANTS = []
