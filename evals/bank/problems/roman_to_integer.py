from evals.bank.controls import PRELUDE, external_code

NUMBER = 13
SLUG = "roman-to-integer"
TITLE = "Roman to Integer"
DIFFICULTY = "Easy"
SPLIT = "test"
METHOD = "romanToInt"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    (("III",), 3, "general"),
    (("LVIII",), 58, "general"),
    (("MCMXCIV",), 1994, "general"),
    (("XLIX",), 49, "general"),
    (("CDXCIV",), 494, "general"),
    (("I",), 1, "edge"),
    (("MMMCMXCIX",), 3999, "edge"),
]

# At most 15 characters, so no algorithm here is slower in any way that matters, and the
# problem has no complexity mutant.
SCALE = ("MMMDCCCLXXXVIII",)
SPACE_SCALE = ("MMMDCCCLXXXVIII",)

SYMBOLS = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
           (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]


def to_roman(number):
    numeral = ""
    for value, symbol in SYMBOLS:
        while number >= value:
            numeral += symbol
            number -= value
    return numeral


NUMERALS = {to_roman(number): number for number in range(1, 4000)}


def reference(s):
    return NUMERALS[s]


def valid(s):
    # 1 <= s.length <= 15, only IVXLCDM, a valid roman numeral in [1, 3999]
    return 1 <= len(s) <= 15 and s in NUMERALS


def generate(rng):
    return (to_roman(rng.choice([rng.randint(1, 3999), rng.randint(1, 50)])),)


MUTANTS = [
    {
        "id": "subtracts-a-repeated-symbol",
        "mutation": "wrong-operator",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def romanToInt(self, s: str) -> int:
        roman = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
        res = 0
        for i in range(len(s)):
            if i + 1 < len(s) and roman[s[i]] <= roman[s[i + 1]]:
                res -= roman[s[i]]
            else:
                res += roman[s[i]]
        return res
''',
    },
    {
        "id": "drops-the-last-symbol",
        "mutation": "off-by-one",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def romanToInt(self, s: str) -> int:
        roman = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
        res = 0
        for a, b in zip(s, s[1:]):
            if roman[a] < roman[b]:
                res -= roman[a]
            else:
                res += roman[a]
        return res
''',
    },
]

CLEAN_VARIANTS = []
