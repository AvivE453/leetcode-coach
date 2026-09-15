# Eval results

Append-only. Each run records the prompt versions it scored, so a prompt change can be read as a movement in these numbers.

Ground truth: feedback labels come from executing each mutant against a test harness (`evals/bank/oracle.py`); enrichment labels come from NeetCode's published Blind 75 sections; retrieval pairs are hand-labelled in `evals/pairs.py`.

---

# Summary

## Feedback quality

Four prompts on two models, measured against three versions of the bank. `bank-v1` was
the first fixture set; `bank-v2` is the same set after three ground-truth defects were
corrected (below); `bank-v3` adds 22 clean controls and 6 regression controls to
`bank-v2` without touching a flawed fixture (below).

| Prompt | Model | Bank | overall recall | bug | complexity | edge-case | false-positive rate |
|---|---|---|---|---|---|---|---|
| `review-v1` | Opus 5 | bank-v1 | 93% (26/28) | 100% (14) | 100% (9) | 60% (5) | 0% (0/13) |
| `review-v2` | Opus 5 | bank-v1 | 93% (26/28) | 100% (14) | 100% (9) | 60% (5) | 8% (1/13) |
| `review-v1` | Opus 5 | bank-v2 | 97% (29/30) | 100% (17) | 100% (9) | 75% (4) | 0% (0/13) |
| `review-v2` | Opus 5 | bank-v2 | 97% (29/30) | 94% (17) | 100% (9) | 100% (4) | 0% (0/13) |
| `review-v3` | Sonnet 5 | bank-v2 | 97% (29/30) | 94% (17) | 100% (9) | 100% (4) | 23% (3/13) |
| `review-v3` | Sonnet 5 | bank-v3 | 97% (29/30) | 94% (17) | 100% (9) | 100% (4) | 11% (4/35) |
| `review-v4` | Sonnet 5 | bank-v3 | **97% (29/30)** | 94% (17) | 100% (9) | 100% (4) | **0% (0/35)** |

Regression controls, `bank-v3` only and scored apart: `review-v3` 50% (3/6), `review-v4`
0% (0/6).

`review-v4` on `claude-sonnet-5` is what the coach ships. `review-v3` added a `strengths`
field so a review also reports what the solution got right; `review-v4` added the
constraints rule described below. The category definitions are otherwise v2's.

**The first two prompt iterations produced no measurable gain.** On the corrected bank v1 and v2
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

## What moved it again: a model switch the eval caught

Moving the coach from `claude-opus-5` to `claude-sonnet-5`, together with `review-v3`,
left recall exactly where it was and took false positives from 0/13 to 3/13. That
matters beyond the report: a review reporting an edge case caps the attempt's grade at 2,
below SM-2's passing line, so a correct solve reviewed that way is rescheduled as a lapse.
The three claims:

- Maximum Subarray and Best Time to Buy and Sell Stock: "an empty list raises
  IndexError", on problems whose constraints state `1 <= length`.
- Climbing Stairs: O(n) called non-optimal because an O(log n) matrix-power solution
  exists, at the `n <= 45` the constraints allow.

All three forget the problem's constraints: ground-truth defect 2 above, made from the
model's side. The model and the prompt changed together, and which one caused it was not
isolated; v3 changed nothing about the categories, so the model is the likelier cause.

**The bank had to grow before a fix could be measured.** With 13 controls each false
positive is 7.7 points, and even 0/13 leaves the 95% (Wilson) upper bound near 23%. So
`bank-v3` added clean controls first, each proven clean by `oracle.verify_clean` - it
passes every test and times within 5× of the canonical - exactly as a mutant is labelled:

- **22 representative controls**: other standard ways to write the optimal solution (a
  two-pass hash map for Two Sum, a shrinking set window for Longest Substring, and so
  on), one or two per problem, pooled with the 13 canonicals into a headline of 35.
- **6 regression controls**: solutions written to probe the false positives just seen -
  seeding from `nums[0]` where the constraints guarantee an element, relying on Two Sum's
  guaranteed answer or Valid Anagram's lowercase alphabet, an O(n) Climbing Stairs. They
  are scored apart, because a prompt revised after reading those failures is expected to
  pass them.

On `bank-v3` the unchanged `review-v3` scored 4/35 (11%), and 3/6 on the regression
controls, all three "nums is empty" claims. That is the baseline. `review-v4` then added
one rule instead of examples: judge issues against the problem's stated constraints and
guarantees, where an input they exclude is not a flaw, and a faster algorithm that makes
no practical difference at the allowed input sizes does not count. It scored 0/35 and
0/6, with recall unchanged at 29/30 and every clean control called `optimal`.

How far to trust that: every headline false positive disappeared and none appeared, but
four discordant fixtures in one run is not conclusive on its own (exact McNemar p ≈ 0.13),
and 0/35 puts the 95% upper bound near 10%, not at zero. The variants were written after
v3's false positives had been read, and two of those three are canonicals in the
headline, so v3 against v4 on the same bank is a fair comparison while the absolute rate
may be optimistic.

On Sonnet 5 the one miss is the same fixture in all three runs, and it is not a category
dispute: `valid-parentheses/no-leftover-check` returns True for `"("`, and the model
reports nothing at all.

## Enrichment — prompt `enrich-v5`

| Metric | `enrich-v2` · Opus 5 | `enrich-v5` · Sonnet 5 | n |
|---|---|---|---|
| `intended_pattern` matches NeetCode's section | 100% | **97%** | 29 |
| `intended_pattern` is among the solution's patterns, on canonical code | 97% | 97% | 29 |

The one `enrich-v5` disagreement is Unique Paths, tagged `dp-1d` where the corpus accepts
`dp-2d`. The corpus solution computes it with a single rolling row, so the tag describes
that code; it still counts as a miss, since `intended_pattern` is a question about the
problem, not the code.

> `enrich-v3` added `intended_secondary_patterns`, a problem's *other* canonical
> approaches. It is **not evaluated**: the corpus labels one canonical section per
> problem, so there is no ground truth for which alternates are also acceptable.
> `enrich-v4` replaced the solution's single `pattern` with `main_patterns`, so the second
> row now reads "`intended_pattern` is among `main_patterns`"; which solutions genuinely
> rest on two patterns has no labels to score against either. `enrich-v5` reworded that
> instruction to drop "usually exactly one", which biased the model toward a single
> pattern (observed on `data/coach.db`: a tree traversal via DFS got only `dfs`, never
> `tree`).

The two-layer design holds: on canonical solutions the layers agree 28 times in 29, as
they should, since a canonical solution *is* the intended approach. Caveat: the accept
sets in `evals/corpus.py` are deliberately generous where a problem has two textbook
approaches, so the first row measures picking a defensible pattern, not matching one
canonical answer.

## Retrieval — recall@5

| Embedding input | `enrich-v2` · Opus 5 | `enrich-v5` · Sonnet 5 |
|---|---|---|
| raw code | 60% | 62% |
| enriched card | 64% | **79%** |
| delta | +5pp | **+17pp** |

29 solutions, 42 labelled pair directions. On `enrich-v2` the cards won modestly; on
`enrich-v5` they win clearly, 33 pair directions to 26. The raw-code column, which no
prompt touches, moved by one pair direction, a fair sense of the noise at this size. Why
the gap widened was not isolated: the cards now carry every main pattern, and the model
writing them changed too. The card misses left are three small clusters where several
labelled pairs compete for five slots: 1-D DP (Climbing Stairs, Coin Change, Combination
Sum), graphs and trees (Course Schedule, Number of Islands, Invert Binary Tree), and two
hashing pairs.

## Known limitations

- **edge-case n=4.** Differences below roughly 25 percentage points in that column are
  a single fixture and should not be read as signal.
- **Bank scope is array/string/DP.** Tree, graph and linked-list problems need
  node-construction harnesses; their patterns are covered only by the enrichment eval.
- **Mutation choice is still authored.** The taxonomy in `evals/bank/problems/__init__.py`
  was fixed before any results were seen and every *label* comes from execution, but
  which mutations got written remains a judgement call and could favour defects this
  model finds easy.
- **So is variant choice, and later.** Every clean control is proven clean by execution,
  but the 28 `bank-v3` variants were written after `review-v3`'s false positives had been
  read, so the absolute false-positive rate may be optimistic even where the comparison
  between prompts on the same bank is fair.
- **Controls are not independent.** The 35 headline controls come from 13 problems, and a
  model that misjudges a problem tends to misjudge every solution to it (both Climbing
  Stairs controls drew the same O(log n) claim under v3), so the effective sample is
  smaller than 35.
- **Two things changed at once, twice.** Opus 5 → Sonnet 5 arrived together with
  `review-v3` and `enrich-v5`, so neither the false-positive regression nor the retrieval
  gain is attributed to the model or the prompt alone.
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


## 2026-09-15 10:57 UTC · model `claude-sonnet-5`

### Feedback quality — prompt `review-v3`

| Metric | Value | n |
|---|---|---|
| recall · bug | 94% | 17 |
| recall · complexity | 100% | 9 |
| recall · edge-case | 100% | 4 |
| **recall · overall** | **97%** | 30 |
| **false-positive rate** (clean controls) | **23%** | 13 |
| verdict `optimal` on clean controls | 77% | 13 |

**Missed flaws**

- valid-parentheses/no-leftover-check — planted bug (input=('(',) expected=False got=True), reported nothing

**False positives** (on code the oracle proved correct)

- maximum-subarray — edge-case: If nums is an empty list, nums[0] raises an IndexError; the code assumes at least one element is present
- climbing-stairs — complexity: The solution runs in O(n) time using simple iteration; the number of distinct step-count values grows like a Fibonacci sequence, which admits an O(log n) solution via matrix exponentiation or fast doubling, so this is not asymptotically optimal though it is correct.
- best-time-to-buy-and-sell-stock — edge-case: If prices is an empty list, prices[0] raises an IndexError; the code never checks for an empty or null input

### Enrichment — prompt `enrich-v5`

| Metric | Value | n |
|---|---|---|
| `intended_pattern` accuracy (vs NeetCode sections) | **97%** | 29 |
| solution pattern == intended, on canonical code | 97% | 29 |

Disagreements: unique-paths: said dp-1d, accepted ['dp-2d']

### Retrieval — recall@5

| Embedding input | recall@5 |
|---|---|
| raw code | 62% |
| enriched card | **79%** |
| delta | +17% |

29 solutions, 42 labelled pair directions.

Card misses: longest-consecutive-sequence -> two-sum; top-k-frequent-elements -> valid-anagram; climbing-stairs -> coin-change; coin-change -> climbing-stairs; coin-change -> combination-sum; combination-sum -> coin-change; course-schedule -> number-of-islands; number-of-islands -> invert-binary-tree; invert-binary-tree -> number-of-islands


## 2026-09-15 11:19 UTC · model `claude-sonnet-5`

### Feedback quality — prompt `review-v3`

| Metric | Value | n |
|---|---|---|
| recall · bug | 94% | 17 |
| recall · complexity | 100% | 9 |
| recall · edge-case | 100% | 4 |
| **recall · overall** | **97%** | 30 |
| **false-positive rate** (clean controls) | **11%** | 35 |
| verdict `optimal` on clean controls | 89% | 35 |
| false-positive rate (regression controls, scored apart) | 50% | 6 |

**Missed flaws**

- valid-parentheses/no-leftover-check — planted bug (input=('(',) expected=False got=True), reported nothing

**False positives** (on code the oracle proved correct)

- maximum-subarray/canonical — edge-case: If nums is an empty list, nums[0] raises an IndexError; the code assumes at least one element is present
- climbing-stairs/canonical — complexity: The solution runs in O(n) time using simple iteration; the number of distinct step-count values grows like a Fibonacci sequence, which admits an O(log n) solution via matrix exponentiation or fast doubling, so this is not asymptotically optimal though it is correct.
- climbing-stairs/base-cases-first — complexity: The iterative loop computes the Fibonacci-like sequence in O(n) time; the asymptotically optimal approach uses matrix exponentiation (or the closed-form Binet formula) to achieve O(log n) time
- best-time-to-buy-and-sell-stock/canonical — edge-case: If prices is an empty list, prices[0] raises an IndexError; the code never checks for an empty or null input


## 2026-09-15 11:24 UTC · model `claude-sonnet-5`

### Feedback quality — prompt `review-v4`

| Metric | Value | n |
|---|---|---|
| recall · bug | 94% | 17 |
| recall · complexity | 100% | 9 |
| recall · edge-case | 100% | 4 |
| **recall · overall** | **97%** | 30 |
| **false-positive rate** (clean controls) | **0%** | 35 |
| verdict `optimal` on clean controls | 100% | 35 |
| false-positive rate (regression controls, scored apart) | 0% | 6 |

**Missed flaws**

- valid-parentheses/no-leftover-check — planted bug (input=('(',) expected=False got=True), reported nothing

