from evals.bank.controls import PRELUDE, external_code

NUMBER = 127
SLUG = "word-ladder"
TITLE = "Word Ladder"
DIFFICULTY = "Hard"
SPLIT = "dev"
METHOD = "ladderLength"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    (("hit", "cog", ["hot", "dot", "dog", "lot", "log", "cog"]), 5, "general"),
    (("hit", "cog", ["hot", "dot", "dog", "lot", "log"]), 0, "general"),
    (("hot", "dog", ["hot", "dog"]), 0, "general"),
    (("abc", "abd", ["abd"]), 2, "general"),
    (("a", "c", ["a", "b", "c"]), 2, "edge"),
]


def word(i, length):
    return "".join("abcdef"[(i // 6**j) % 6] for j in range(length))


SCALE = ("aaaaa", word(999, 5), [word(i, 5) for i in range(1000)])
SPACE_SCALE = ("aaaaa", word(4999, 5), [word(i, 5) for i in range(5000)])


def reference(beginWord, endWord, wordList):
    def adjacent(a, b):
        return sum(x != y for x, y in zip(a, b)) == 1

    frontier, seen, steps = [beginWord], {beginWord}, 1
    while frontier:
        if endWord in frontier:
            return steps
        frontier = [w for w in wordList if w not in seen and any(adjacent(w, f) for f in frontier)]
        seen.update(frontier)
        steps += 1
    return 0


def generate(rng):
    # constraints: 1 <= beginWord.length <= 10, endWord and every word have that length,
    # 1 <= wordList.length <= 5000, distinct words, beginWord != endWord
    every = [word(i, 3)[:3] for i in range(216) if set(word(i, 3)) <= set("abc")]
    begin, end = rng.sample(every, 2)
    return (begin, end, rng.sample(every, rng.randint(1, 8)))


MUTANTS = [
    {
        "id": "counts-steps-not-words",
        "mutation": "off-by-one",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def ladderLength(self, beginWord: str, endWord: str, wordList: List[str]) -> int:
        if endWord not in wordList:
            return 0

        nei = collections.defaultdict(list)
        wordList.append(beginWord)
        for word in wordList:
            for j in range(len(word)):
                pattern = word[:j] + "*" + word[j + 1 :]
                nei[pattern].append(word)

        visit = set([beginWord])
        q = deque([beginWord])
        res = 0
        while q:
            for i in range(len(q)):
                word = q.popleft()
                if word == endWord:
                    return res
                for j in range(len(word)):
                    pattern = word[:j] + "*" + word[j + 1 :]
                    for neiWord in nei[pattern]:
                        if neiWord not in visit:
                            visit.add(neiWord)
                            q.append(neiWord)
            res += 1
        return 0
''',
    },
    {
        "id": "words-are-revisited",
        "mutation": "missing-guard",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def ladderLength(self, beginWord: str, endWord: str, wordList: List[str]) -> int:
        if endWord not in wordList:
            return 0

        nei = collections.defaultdict(list)
        wordList.append(beginWord)
        for word in wordList:
            for j in range(len(word)):
                pattern = word[:j] + "*" + word[j + 1 :]
                nei[pattern].append(word)

        q = deque([beginWord])
        res = 1
        while q:
            for i in range(len(q)):
                word = q.popleft()
                if word == endWord:
                    return res
                for j in range(len(word)):
                    pattern = word[:j] + "*" + word[j + 1 :]
                    for neiWord in nei[pattern]:
                        q.append(neiWord)
            res += 1
        return 0
''',
    },
    {
        "id": "compare-every-pair-of-words",
        "mutation": "brute-force",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def ladderLength(self, beginWord: str, endWord: str, wordList: List[str]) -> int:
        if endWord not in wordList:
            return 0

        words = wordList + [beginWord]
        nei = {w: [] for w in words}
        for a in words:
            for b in words:
                if sum(x != y for x, y in zip(a, b)) == 1:
                    nei[a].append(b)

        visit = {beginWord}
        q = deque([beginWord])
        res = 1
        while q:
            for _ in range(len(q)):
                word = q.popleft()
                if word == endWord:
                    return res
                for neiWord in nei[word]:
                    if neiWord not in visit:
                        visit.add(neiWord)
                        q.append(neiWord)
            res += 1
        return 0
''',
    },
]

CLEAN_VARIANTS = []
