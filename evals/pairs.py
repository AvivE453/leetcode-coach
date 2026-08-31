"""Labelled "these two should retrieve each other" pairs, drawn from the corpus.

A pair is listed only when the two problems share a *technique*, not merely a
topic - the retrieval feature exists to answer "have I solved something like
this?", so 3Sum and Two Sum belong together while Two Sum and Product of Array
Except Self (both "arrays") do not.
"""

SIMILAR_PAIRS = [
    ("two-sum", "3sum"),
    ("two-sum", "contains-duplicate"),
    ("two-sum", "longest-consecutive-sequence"),
    ("contains-duplicate", "valid-anagram"),
    ("valid-anagram", "top-k-frequent-elements"),
    ("contains-duplicate", "top-k-frequent-elements"),
    ("climbing-stairs", "house-robber"),
    ("climbing-stairs", "coin-change"),
    ("house-robber", "coin-change"),
    ("house-robber", "maximum-subarray"),
    ("maximum-subarray", "best-time-to-buy-and-sell-stock"),
    ("coin-change", "combination-sum"),
    ("climbing-stairs", "unique-paths"),
    ("merge-intervals", "insert-interval"),
    ("number-of-islands", "course-schedule"),
    ("invert-binary-tree", "binary-tree-level-order-traversal"),
    ("number-of-islands", "invert-binary-tree"),
    ("reverse-linked-list", "linked-list-cycle"),
    ("find-minimum-in-rotated-sorted-array", "search-in-rotated-sorted-array"),
    ("longest-substring-without-repeating-characters", "best-time-to-buy-and-sell-stock"),
    ("number-of-1-bits", "counting-bits"),
]
