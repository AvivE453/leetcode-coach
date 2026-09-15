from evals.bank.controls import PRELUDE, external_code

NUMBER = 4
SLUG = "median-of-two-sorted-arrays"
TITLE = "Median of Two Sorted Arrays"
DIFFICULTY = "Hard"
SPLIT = "test"
METHOD = "findMedianSortedArrays"

CANONICAL = external_code("neetcode", NUMBER)

TESTS = [
    (([1, 3], [2]), 2.0, "general"),
    (([1, 2], [3, 4]), 2.5, "general"),
    (([1, 2], [1, 2]), 1.5, "general"),
    (([1, 1, 1], [5, 6, 7]), 3.0, "general"),
    (([5, 6, 7, 8, 9], [1]), 6.5, "general"),
    (([], [1]), 1.0, "edge"),
    (([2], []), 2.0, "edge"),
]

SCALE = (list(range(0, 2000, 2)), list(range(1, 2000, 2)))
SPACE_SCALE = (list(range(0, 2000, 2)), list(range(1, 2000, 2)))


def normalize(median):
    """LeetCode compares the median as a number, so an odd total may come back as an int."""
    return float(median)


def reference(nums1, nums2):
    merged = sorted(nums1 + nums2)
    mid = len(merged) // 2
    return merged[mid] if len(merged) % 2 else (merged[mid - 1] + merged[mid]) / 2


def generate(rng):
    # constraints: 0 <= m, n <= 1000, 1 <= m + n, both sorted, -10^6 <= values <= 10^6
    while True:
        nums1 = sorted(rng.randint(-9, 9) for _ in range(rng.randint(0, 5)))
        nums2 = sorted(rng.randint(-9, 9) for _ in range(rng.randint(0, 5)))
        if nums1 or nums2:
            return (nums1, nums2)


MUTANTS = [
    {
        "id": "searches-the-longer-array",
        "mutation": "missing-precondition",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def findMedianSortedArrays(self, nums1: List[int], nums2: List[int]) -> float:
        A, B = nums1, nums2
        total = len(nums1) + len(nums2)
        half = total // 2

        l, r = 0, len(A) - 1
        while True:
            i = (l + r) // 2  # A
            j = half - i - 2  # B

            Aleft = A[i] if i >= 0 else float("-infinity")
            Aright = A[i + 1] if (i + 1) < len(A) else float("infinity")
            Bleft = B[j] if j >= 0 else float("-infinity")
            Bright = B[j + 1] if (j + 1) < len(B) else float("infinity")

            # partition is correct
            if Aleft <= Bright and Bleft <= Aright:
                # odd
                if total % 2:
                    return min(Aright, Bright)
                # even
                return (max(Aleft, Bleft) + min(Aright, Bright)) / 2
            elif Aleft > Bright:
                r = i - 1
            else:
                l = i + 1
''',
    },
    {
        "id": "odd-total-takes-the-left-side",
        "mutation": "off-by-one",
        "intended": "bug",
        "code": PRELUDE + '''\
class Solution:
    def findMedianSortedArrays(self, nums1: List[int], nums2: List[int]) -> float:
        A, B = nums1, nums2
        total = len(nums1) + len(nums2)
        half = total // 2

        if len(B) < len(A):
            A, B = B, A

        l, r = 0, len(A) - 1
        while True:
            i = (l + r) // 2  # A
            j = half - i - 2  # B

            Aleft = A[i] if i >= 0 else float("-infinity")
            Aright = A[i + 1] if (i + 1) < len(A) else float("infinity")
            Bleft = B[j] if j >= 0 else float("-infinity")
            Bright = B[j + 1] if (j + 1) < len(B) else float("infinity")

            # partition is correct
            if Aleft <= Bright and Bleft <= Aright:
                # odd
                if total % 2:
                    return max(Aleft, Bleft)
                # even
                return (max(Aleft, Bleft) + min(Aright, Bright)) / 2
            elif Aleft > Bright:
                r = i - 1
            else:
                l = i + 1
''',
    },
    {
        "id": "merge-both-arrays",
        "mutation": "brute-force",
        "intended": "complexity",
        "code": PRELUDE + '''\
class Solution:
    def findMedianSortedArrays(self, nums1: List[int], nums2: List[int]) -> float:
        merged = []
        i = j = 0
        while i < len(nums1) or j < len(nums2):
            if j == len(nums2) or (i < len(nums1) and nums1[i] <= nums2[j]):
                merged.append(nums1[i])
                i += 1
            else:
                merged.append(nums2[j])
                j += 1
        mid = len(merged) // 2
        return merged[mid] if len(merged) % 2 else (merged[mid - 1] + merged[mid]) / 2
''',
    },
]

CLEAN_VARIANTS = []
