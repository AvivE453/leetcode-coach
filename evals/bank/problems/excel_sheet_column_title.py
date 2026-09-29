from evals.bank.controls import PRELUDE, external_code

NUMBER = 168
SLUG = "excel-sheet-column-title"
TITLE = "Excel Sheet Column Title"
DIFFICULTY = "Easy"
SPLIT = "test"
METHOD = "convertToTitle"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    ((28,), "AB", "general"),
    ((701,), "ZY", "general"),
    ((26,), "Z", "general"),
    ((52,), "AZ", "general"),
    ((703,), "AAA", "general"),
    ((1,), "A", "edge"),
    ((2**31 - 1,), "FXSHRXW", "edge"),
]

SCALE = (2**31 - 1,)
SPACE_SCALE = (2**31 - 1,)


def reference(columnNumber):
    # Titles of one letter number 26, of two 26^2, and so on: find the title's length,
    # then its offset among titles of that length is a plain base-26 number.
    length, first = 1, 1
    while columnNumber >= first + 26**length:
        first += 26**length
        length += 1
    offset = columnNumber - first
    letters = []
    for _ in range(length):
        offset, digit = divmod(offset, 26)
        letters.append(chr(ord("A") + digit))
    return "".join(reversed(letters))


def valid(columnNumber):
    # 1 <= columnNumber <= 2^31 - 1
    return 1 <= columnNumber <= 2**31 - 1


def generate(rng):
    power = 26 ** rng.randint(1, 6)
    return (rng.choice([rng.randint(1, 800), rng.randint(1, 2**31 - 1), power, power + 1, power - 1]),)


def is_edge(columnNumber):
    return columnNumber in (1, 2**31 - 1)


MUTANTS = [
    {
        "id": "zero-based-digits-without-the-shift",
        "mutation": "off-by-one",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def convertToTitle(self, columnNumber: int) -> str:
        res = ""
        while columnNumber > 0:
            remainder = columnNumber % 26
            res += chr(ord('A') + remainder - 1)
            columnNumber //= 26
        return res[::-1]
''',
    },
    {
        "id": "divides-before-shifting",
        "mutation": "off-by-one",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def convertToTitle(self, columnNumber: int) -> str:
        res = ""
        while columnNumber > 0:
            remainder = (columnNumber - 1) % 26
            res += chr(ord('A') + remainder)
            columnNumber = columnNumber // 26
        return res[::-1]
''',
    },
]

CLEAN_VARIANTS = []
