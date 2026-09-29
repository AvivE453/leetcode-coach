from evals.bank.controls import PRELUDE, external_code

NUMBER = 838
SLUG = "push-dominoes"
TITLE = "Push Dominoes"
DIFFICULTY = "Medium"
SPLIT = "test"
METHOD = "pushDominoes"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    (("RR.L",), "RR.L", "general"),
    ((".L.R...LR..L..",), "LL.RR.LLRRLL..", "general"),
    (("R...L",), "RR.LL", "general"),
    (("R..L",), "RRLL", "general"),
    (("..R..",), "..RRR", "general"),
    (("..L..",), "LLL..", "general"),
    ((".",), ".", "edge"),
    (("L",), "L", "edge"),
    (("R",), "R", "edge"),
]

SCALE = (("R" + "." * 998 + "L") * 3,)
SPACE_SCALE = (("R" + "." * 998 + "L") * 3,)


def reference(dominoes):
    state = list(dominoes)
    while True:
        pushed = state[:]
        for i, domino in enumerate(state):
            if domino != ".":
                continue
            from_left = i > 0 and state[i - 1] == "R"
            from_right = i + 1 < len(state) and state[i + 1] == "L"
            if from_left != from_right:
                pushed[i] = "R" if from_left else "L"
        if pushed == state:
            return "".join(state)
        state = pushed


def valid(dominoes):
    # 1 <= n <= 10^5, dominoes[i] is 'L', 'R' or '.'
    return 1 <= len(dominoes) <= 10**5 and set(dominoes) <= set("LR.")


def generate(rng):
    return ("".join(rng.choice("..LR") for _ in range(rng.randint(1, 10))),)


MUTANTS = [
    {
        "id": "topples-the-balanced-middle",
        "mutation": "off-by-one",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def pushDominoes(self, dominoes: str) -> str:
        ans = list(dominoes)
        L = -1
        R = -1

        for i in range(len(dominoes) + 1):
            if i == len(dominoes) or dominoes[i] == 'R':
                if L < R:
                    while R < i:
                        ans[R] = 'R'
                        R += 1
                R = i
            elif dominoes[i] == 'L':
                if R < L or (L, R) == (-1, -1):
                    if (L, R) == (-1, -1):
                        L += 1
                    while L < i:
                        ans[L] = 'L'
                        L += 1
                else:
                    l = R + 1
                    r = i - 1
                    while l <= r:
                        ans[l] = 'R'
                        ans[r] = 'L'
                        l += 1
                        r -= 1
                L = i

        return ''.join(ans)
''',
    },
    {
        "id": "simulates-each-second",
        "mutation": "brute-force",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def pushDominoes(self, dominoes: str) -> str:
        state = list(dominoes)
        changed = True
        while changed:
            changed = False
            nxt = state[:]
            for i in range(len(state)):
                if state[i] != '.':
                    continue
                left = i > 0 and state[i - 1] == 'R'
                right = i + 1 < len(state) and state[i + 1] == 'L'
                if left and not right:
                    nxt[i] = 'R'
                    changed = True
                elif right and not left:
                    nxt[i] = 'L'
                    changed = True
            state = nxt
        return ''.join(state)
''',
    },
]

CLEAN_VARIANTS = []
