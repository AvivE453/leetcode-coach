NUMBER = 49
SLUG = "group-anagrams"
TITLE = "Group Anagrams"
DIFFICULTY = "Medium"
SPLIT = "test"
METHOD = "groupAnagrams"

# NeetCode's solution defines groupAnagrams twice, so it was rejected, and this one is
# authored: in the test split it is the timing reference for the mutants, not a control.
CANONICAL = '''\
class Solution:
    def groupAnagrams(self, strs):
        groups = {}
        for s in strs:
            count = [0] * 26
            for ch in s:
                count[ord(ch) - ord("a")] += 1
            groups.setdefault(tuple(count), []).append(s)
        return list(groups.values())
'''

TESTS = [
    ((["eat", "tea", "tan", "ate", "nat", "bat"],), [["bat"], ["nat", "tan"], ["ate", "eat", "tea"]], "general"),
    ((["abb", "aab", "bab"],), [["aab"], ["abb", "bab"]], "general"),
    ((["ad", "bc"],), [["ad"], ["bc"]], "general"),
    ((["a"],), [["a"]], "edge"),
    (([""],), [[""]], "edge"),
    ((["", "b", ""],), [["", ""], ["b"]], "edge"),
]

SCALE = (["".join(chr(97 + (i // 26**j) % 26) for j in range(3)) for i in range(1000)],)
SPACE_SCALE = (["".join(chr(97 + (i // 26**j) % 26) for j in range(5)) for i in range(10_000)],)


def normalize(groups):
    """LeetCode accepts the groups, and the words in each, in any order."""
    return sorted(sorted(group) for group in groups)


def reference(strs):
    groups = []
    for s in strs:
        for group in groups:
            if sorted(group[0]) == sorted(s):
                group.append(s)
                break
        else:
            groups.append([s])
    return groups


def generate(rng):
    # constraints: 1 <= strs.length <= 10^4, 0 <= strs[i].length <= 100, lowercase letters
    return (["".join(rng.choice("abcd") for _ in range(rng.randint(0, 3))) for _ in range(rng.randint(1, 8))],)


MUTANTS = [
    {
        "id": "letter-set-key",
        "mutation": "weaker-structure",
        "intended": "bug",
        "code": '''\
class Solution:
    def groupAnagrams(self, strs):
        groups = {}
        for s in strs:
            groups.setdefault(frozenset(s), []).append(s)
        return list(groups.values())
''',
    },
    {
        "id": "character-sum-key",
        "mutation": "weaker-structure",
        "intended": "bug",
        "code": '''\
class Solution:
    def groupAnagrams(self, strs):
        groups = {}
        for s in strs:
            groups.setdefault(sum(ord(ch) for ch in s), []).append(s)
        return list(groups.values())
''',
    },
    {
        "id": "compare-with-every-group",
        "mutation": "brute-force",
        "intended": "complexity",
        "code": '''\
class Solution:
    def groupAnagrams(self, strs):
        groups = []
        for s in strs:
            for group in groups:
                if sorted(group[0]) == sorted(s):
                    group.append(s)
                    break
            else:
                groups.append([s])
        return groups
''',
    },
]

CLEAN_VARIANTS = []
