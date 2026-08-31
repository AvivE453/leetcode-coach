# Eval results

Append-only. Each run records the prompt versions it scored, so a prompt change can be read as a movement in these numbers.

Ground truth: feedback labels come from executing each mutant against a test harness (`evals/bank/oracle.py`); enrichment labels come from NeetCode's published Blind 75 sections; retrieval pairs are hand-labelled in `evals/pairs.py`.

---

# Summary

## Feedback quality

Two prompt iterations, measured against two versions of the bank. `bank-v1` was the
first fixture set; `bank-v2` is the same set after three ground-truth defects were
corrected (below).

| Prompt | Bank | overall recall | bug | complexity | edge-case | false-positive rate |
|---|---|---|---|---|---|---|
| `review-v1` | bank-v1 | 93% (26/28) | 100% (14) | 100% (9) | 60% (5) | 0% |
| `review-v2` | bank-v1 | 93% (26/28) | 100% (14) | 100% (9) | 60% (5) | 8% |
| `review-v1` | bank-v2 | **97% (29/30)** | 100% (17) | 100% (9) | 75% (4) | 0% |
| `review-v2` | bank-v2 | **97% (29/30)** | 94% (17) | 100% (9) | 100% (4) | 0% |

**The prompt iterations produced no measurable gain.** On the corrected bank v1 and v2
tie at 29/30, and they differ only in *which* fixture they miss — mirror images of the
same dispute over where `bug` ends and `edge-case` begins:

- `review-v1` calls the division-by-zero in Product of Array Except Self a `bug`; the
  oracle calls it `edge-case` because only the zero-containing input fails.
- `review-v2` calls the missing stack-underflow guard in Valid Parentheses an
  `edge-case`; the oracle calls it a `bug` because a lone `)` is a representative input.

Both readings are defensible. At n=30 the eval cannot separate the two prompts, and
saying so is more useful than picking the flattering framing. `review-v2` is kept
because mutually exclusive category definitions are correct by design, not because the
data prefers it.

## What actually moved the number

The 93% → 97% improvement came from **fixing the eval, not the prompt** — three
independent ground-truth defects, every one of them found because the model disagreed
with a label and the disagreement turned out to be the model's point:

1. **Boundary tests that weren't boundaries.** Different-length strings for
   `isAnagram`, an unmatched bracket for `isValid` — ordinary inputs marked `edge`
   because I was thinking about which mutant I wanted to catch rather than what the
   input actually is.
2. **Tests that violate the problem's constraints.** Empty arrays fed to Contains
   Duplicate, House Robber and Merge Intervals, whose LeetCode constraints all state
   `1 <= length`. A defect on an input the problem excludes is not a defect. Removing
   those tests made the three corresponding mutants indistinguishable from the
   canonical solution, and `oracle.classify` discarded them automatically — the
   discard rule doing exactly its job.
3. **A "clean" control that was not clean.** The Best Time to Buy and Sell Stock
   canonical iterated `prices[1:]`, allocating an O(n) copy. The model reported it as
   a space-complexity issue and was scored as a false positive *for being right*.

## Enrichment — prompt `enrich-v2`

| Metric | Value | n |
|---|---|---|
| `intended_pattern` matches NeetCode's section | **100%** | 29 |
| solution `pattern` == `intended_pattern` on canonical code | 97% | 29 |

The two-layer design holds: on canonical solutions the layers agree (as they should,
since a canonical solution *is* the intended approach), and the one disagreement is
Best Time to Buy and Sell Stock, where NeetCode files the problem under Sliding Window
while the solution reads as a single greedy pass — both defensible. Caveat: the accept
sets in `evals/corpus.py` are deliberately generous where a problem has two textbook
approaches, so 100% means "never picked an indefensible pattern", not "matched one
canonical answer".

## Retrieval — recall@5

| Embedding input | recall@5 |
|---|---|
| raw code | 60% |
| enriched card | **64%** |
| delta | **+5pp** |

29 solutions, 42 labelled pair directions. Enriched cards win, but **modestly** — this
validates design decision #2 weakly, not strongly. Both variants fail on the same
cluster: the 1-D DP family (Climbing Stairs, Coin Change, House Robber, Combination
Sum), where four labelled pairs compete for five result slots against a corpus dense
in DP problems. A larger corpus would likely widen the gap, since pattern language is
what separates problems that share no vocabulary.

## Known limitations

- **edge-case n=4.** Differences below roughly 25 percentage points in that column are
  a single fixture and should not be read as signal.
- **Bank scope is array/string/DP.** Tree, graph and linked-list problems need
  node-construction harnesses; their patterns are covered only by the enrichment eval.
- **Mutation choice is still authored.** The taxonomy in `evals/bank/problems/__init__.py`
  was fixed before any results were seen and every *label* comes from execution, but
  which mutations got written remains a judgement call and could favour defects this
  model finds easy.
- **Single run per cell.** No repeated sampling, so run-to-run variance is unmeasured.

---

# Run log

## 2026-08-31 14:21 UTC · model `claude-opus-5`

### Feedback quality — prompt `review-v1`

| Metric | Value | n |
|---|---|---|
| recall · bug | 100% | 14 |
| recall · complexity | 100% | 9 |
| recall · edge-case | 60% | 5 |
| **recall · overall** | **93%** | 28 |
| **false-positive rate** (clean controls) | **0%** | 13 |
| verdict `optimal` on clean controls | 100% | 13 |

Missed flaws: valid-parentheses/no-leftover-check (planted edge-case, reported ['bug']); product-of-array-except-self/division (planted edge-case, reported ['bug'])

### Enrichment — prompt `enrich-v2`

| Metric | Value | n |
|---|---|---|
| `intended_pattern` accuracy (vs NeetCode sections) | **100%** | 29 |
| solution pattern == intended, on canonical code | 97% | 29 |

### Retrieval — recall@5

| Embedding input | recall@5 |
|---|---|
| raw code | 60% |
| enriched card | **64%** |
| delta | +5% |

29 solutions, 42 labelled pair directions.

Card misses: longest-consecutive-sequence -> two-sum; contains-duplicate -> valid-anagram; top-k-frequent-elements -> valid-anagram; climbing-stairs -> coin-change; coin-change -> climbing-stairs; house-robber -> coin-change; coin-change -> house-robber; house-robber -> maximum-subarray; maximum-subarray -> house-robber; coin-change -> combination-sum; combination-sum -> coin-change; course-schedule -> number-of-islands; number-of-islands -> invert-binary-tree; invert-binary-tree -> number-of-islands; longest-substring-without-repeating-characters -> best-time-to-buy-and-sell-stock


## 2026-08-31 14:24 UTC · model `claude-opus-5`

### Feedback quality — prompt `review-v2`

| Metric | Value | n |
|---|---|---|
| recall · bug | 100% | 14 |
| recall · complexity | 100% | 9 |
| recall · edge-case | 60% | 5 |
| **recall · overall** | **93%** | 28 |
| **false-positive rate** (clean controls) | **8%** | 13 |
| verdict `optimal` on clean controls | 92% | 13 |

Missed flaws: valid-parentheses/no-leftover-check (planted edge-case, reported ['bug']); valid-anagram/no-length-check (planted edge-case, reported ['bug'])

False positives: best-time-to-buy-and-sell-stock (complexity)


## 2026-08-31 14:32 UTC · model `claude-opus-5`

### Feedback quality — prompt `review-v2`

| Metric | Value | n |
|---|---|---|
| recall · bug | 94% | 17 |
| recall · complexity | 100% | 9 |
| recall · edge-case | 71% | 7 |
| **recall · overall** | **91%** | 33 |
| **false-positive rate** (clean controls) | **8%** | 13 |
| verdict `optimal` on clean controls | 92% | 13 |

Missed flaws: valid-parentheses/no-underflow-guard (planted bug, reported ['edge-case']); merge-intervals/assumes-nonempty (planted edge-case, reported nothing); house-robber/assumes-nonempty (planted edge-case, reported nothing)

False positives: best-time-to-buy-and-sell-stock (complexity)


## 2026-08-31 14:41 UTC · model `claude-opus-5`

### Feedback quality — prompt `review-v2`

| Metric | Value | n |
|---|---|---|
| recall · bug | 94% | 17 |
| recall · complexity | 100% | 9 |
| recall · edge-case | 100% | 4 |
| **recall · overall** | **97%** | 30 |
| **false-positive rate** (clean controls) | **0%** | 13 |
| verdict `optimal` on clean controls | 100% | 13 |

Missed flaws: valid-parentheses/no-underflow-guard (planted bug, reported ['edge-case'])


## 2026-08-31 14:43 UTC · model `claude-opus-5`

### Feedback quality — prompt `review-v1`

| Metric | Value | n |
|---|---|---|
| recall · bug | 100% | 17 |
| recall · complexity | 100% | 9 |
| recall · edge-case | 75% | 4 |
| **recall · overall** | **97%** | 30 |
| **false-positive rate** (clean controls) | **0%** | 13 |
| verdict `optimal` on clean controls | 100% | 13 |

Missed flaws: product-of-array-except-self/division (planted edge-case, reported ['bug'])

