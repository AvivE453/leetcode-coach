# Eval results

Append-only. Each run records the prompt versions it scored, so a prompt change can be read as a movement in these numbers.

Ground truth: feedback labels come from executing each mutant against a test harness (`evals/bank/oracle.py`); enrichment labels come from NeetCode's published Blind 75 sections; retrieval pairs are hand-labelled in `evals/pairs.py`.

---

# Summary

## Feedback quality

### Held out: 82% recall, 20% false positives

`bank-v4` holds 60 problems. The 13 that every row further down was measured on, and that
`review-v4` was written against, sit in its `dev` split with 22 new ones. The other 25 new
problems are a `test` split no prompt has been tuned on - 3 Easy, 14 Medium, 8 Hard,
assigned mechanically (within each difficulty, sorted by number, alternating, test
first). Every clean control in it was written outside this repo: NeetCode and walkccc
solutions copied unmodified at pinned commits, and the author's own clean solves. The
bank, tests and mutants included, was committed (`7350811`) before any review call on
it. This is the number to quote:

| `review-v4` · Sonnet 5 · `bank-v4` test | Result | 95% CI (Wilson) |
|---|---|---|
| **recall on planted flaws** | **82%** (59/72) | 72–89% |
| · bug | 75% (33/44) | 61–85% |
| · complexity | 90% (19/21) | 71–97% |
| · edge-case | 100% (7/7) | 65–100% |
| **false-positive rate on clean controls** | **20%** (10/49) | 12–34% |
| · NeetCode | 22% (5/23) | 10–42% |
| · walkccc | 14% (3/22) | 5–33% |
| · the author's own solves | 50% (2/4) | 15–85% |

By difficulty, recall and false positives: Easy 7/8 and 3/8, Medium 32/41 and 5/27, Hard
20/23 and 2/14. At this size the reviewer does no worse on Hard problems.

**The tuned numbers did not transfer.** On the 13 problems it was written against,
`review-v4` scored 97% (29/30) and 0% (0/35). The false-positive gap is well outside
chance (Fisher exact p = 0.004), the recall gap borderline (p = 0.06). The two sets
differ in more than tuning - the test problems are harder, and none of their code was
written here - so the drop is not attributed to overfitting alone. What it does settle is
which number describes the reviewer.

**What the revealed lines show.** This reading came after the run, from the bank's
authors - Claude Code among them, the same model family as the reviewer - so check it
against the run log below; it does not correct the number.

- **8 of the 10 false positives are defensible claims.** Five say published code uses
  more space than it needs: a filtered, reversed copy in NeetCode's Valid Palindrome
  where two pointers need O(1), and a full table for Longest Common Subsequence and
  Distinct Subsequences (canonical and walkccc for each) where one rolling row is enough.
  The canonical does the same in each, and the oracle measures memory only against the
  canonical, so it passed them as clean. Two more are space remarks on the author's own
  solves, whose code and claims stay private; read against that code, they hold up on
  the same grounds. The eighth is Pacific Atlantic's recursive DFS, which can exceed
  CPython's default recursion limit on a 200×200 grid: true in plain Python, and hidden
  by the oracle raising that limit. The other two are wrong or immaterial: Group Anagrams
  (walkccc) returning `dict.values()` called a bug, alongside a sorted-string key called
  non-optimal at k ≤ 100, and slice copies in House Robber II at n ≤ 100.
- **Of the 13 misses, 2 are the old category dispute.** Spiral Matrix and Pacific
  Atlantic are reported as `edge-case`, but a LeetCode example input fails, so the oracle
  says `bug`. **One is a label the prompt's own constraints rule argues against:**
  counting all 32 bits of every number (Counting Bits) is 20× slower than the DP at scale,
  yet takes about 0.14 s at the largest n allowed.
- **The other 10 are plain misses, and 8 of them report nothing at all on a bug that fails
  one of LeetCode's own examples:** the flipped comparison in Container With Most Water,
  two mistakes in Trapping Rain Water's pointers, both Insert Interval mutants, Minimum
  Window Substring, Longest Consecutive Sequence, and buckets walked from the least
  frequent in Top K Frequent Elements. Each is one small edit to a published NeetCode
  solution, which fits a reviewer that recognises a famous solution instead of tracing
  it. This run cannot test that guess, since the dev mutants came from code written here.
  The last two are a DP that takes the best neighbour on a match (Longest Common
  Subsequence, where only a space remark came back) and a loop over `nums` instead of its
  set (Longest Consecutive Sequence), which turns quadratic when a sequence start repeats.

**What follows.** The test split is revealed, so it is spent: a `review-v5` needs new test
problems before its number means anything. And before a false-positive rate can be read
as the reviewer's error rate alone, "clean" has to mean optimal, not merely no worse than
the canonical.

### How it got here, on the dev problems

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

- **"Clean" means no worse than the canonical, not optimal.** The oracle times and
  measures a control against its problem's canonical, and runs everything with a raised
  recursion limit, so code that shares the canonical's extra space or recursion depth
  passes as clean. By the reading above, that is 8 of the 10 false positives on the
  `bank-v4` test split.
- **Small categories.** edge-case has n=4 on dev and n=7 on test; there a difference of
  15-25 points is a single fixture and should not be read as signal.
- **Bank scope is plain-value problems.** Tree and linked-list problems need
  node-construction harnesses; their patterns are covered only by the enrichment eval.
- **Mutation choice is still authored.** The taxonomy in `evals/bank/problems/__init__.py`
  was fixed before any results were seen and every *label* comes from execution, but
  which mutations got written remains a judgement call and could favour defects this
  model finds easy - or, on the test split, hard: most test mutants are small edits to a
  famous published solution.
- **Dev controls were written after the failures.** Every clean control is proven clean
  by execution, but the 28 `bank-v3` variants were written after `review-v3`'s false
  positives had been read, so dev's false-positive rate may be optimistic even where the
  comparison between prompts on the same bank is fair. That is why the test split scores
  no code written here.
- **Controls are not independent.** The 49 test controls come from 25 problems, and 7 of
  the 10 false positives sit on three of them; a model that misjudges a problem tends to
  misjudge every solution to it (both Climbing Stairs controls drew the same O(log n)
  claim under v3). The effective sample is smaller than the count.
- **The held-out comparison is confounded.** The test problems are harder than the dev
  ones and their code was written elsewhere, so the drop from dev to test is not
  attributed to prompt tuning alone.
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


## 2026-09-15 20:33 UTC · model `claude-sonnet-5`

### Feedback quality — prompt `review-v4` · split `test` · details hidden

| Metric | Value | n |
|---|---|---|
| recall · bug | 75% | 44 |
| recall · complexity | 90% | 21 |
| recall · edge-case | 100% | 7 |
| **recall · overall** | **82%** | 72 |
| **false-positive rate** (clean controls) | **20%** | 49 |
| false-positive rate · aviv | 50% | 4 |
| false-positive rate · neetcode | 22% | 23 |
| false-positive rate · walkccc | 14% | 22 |
| verdict `optimal` on clean controls | 78% | 49 |

_Misses and false positives not shown: `--reveal-test` shows them, and spends this split for prompt work._


## 2026-09-15 20:37 UTC · model `claude-sonnet-5`

### Feedback quality — prompt `review-v4` · split `test` · details revealed

| Metric | Value | n |
|---|---|---|
| recall · bug | 75% | 44 |
| recall · complexity | 90% | 21 |
| recall · edge-case | 100% | 7 |
| **recall · overall** | **82%** | 72 |
| **false-positive rate** (clean controls) | **20%** | 49 |
| false-positive rate · aviv | 50% | 4 |
| false-positive rate · neetcode | 22% | 23 |
| false-positive rate · walkccc | 14% | 22 |
| verdict `optimal` on clean controls | 78% | 49 |

**Missed flaws**

- container-with-most-water/move-the-taller-side — planted bug (input=([1, 8, 6, 2, 5, 4, 8, 3, 7],) expected=49 got=8), reported nothing
- trapping-rain-water/moves-the-higher-wall — planted bug (input=([0, 1, 0, 2, 1, 0, 1, 3, 2, 1, 2, 1],) expected=6 got=17), reported nothing
- trapping-rain-water/water-counted-before-the-wall-rises — planted bug (input=([0, 1, 0, 2, 1, 0, 1, 3, 2, 1, 2, 1],) expected=6 got=1), reported nothing
- spiral-matrix/no-break-between-halves — planted bug (input=([[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12]],) expected=[1, 2, 3, 4, 8, 12, 11, 10, 9, 5, 6, 7] got=[1, 2, 3, 4, 8, 12, 11, 10, 9, 5, 6, 7, 6]), reported ['edge-case']
- insert-interval/touching-does-not-merge — planted bug (input=([[1, 2], [3, 5], [6, 7], [8, 10], [12, 16]], [4, 8]) expected=[[1, 2], [3, 10], [12, 16]] got=[[1, 2], [3, 8], [8, 10], [12, 16]]), reported nothing
- insert-interval/keeps-the-new-start — planted bug (input=([[1, 3], [6, 9]], [2, 5]) expected=[[1, 5], [6, 9]] got=[[2, 5], [6, 9]]), reported nothing
- minimum-window-substring/records-after-shrinking — planted bug (input=('ADOBECODEBANC', 'ABC') expected='BANC' got='ANC'), reported nothing
- longest-consecutive-sequence/skips-the-next-number — planted bug (input=([100, 4, 200, 1, 3, 2],) expected=4 got=3), reported nothing
- longest-consecutive-sequence/walks-every-duplicate — planted complexity (858x slower at scale (203ms vs 0.236ms)), reported nothing
- counting-bits/thirty-two-bits-each — planted complexity (20x slower at scale (137ms vs 6.76ms)), reported nothing
- top-k-frequent-elements/least-frequent-first — planted bug (input=([1, 1, 1, 2, 2, 3], 2) expected=[1, 2] got=[3, 2]), reported nothing
- pacific-atlantic-water-flow/water-needs-a-strict-drop — planted bug (input=([[1, 2, 2, 3, 5], [3, 2, 3, 4, 4], [2, 4, 5, 3, 1], [6, 7, 1, 4, 5], [5, 1, 1, 2, 4]],) expected=[[0, 4], [1, 3], [1, 4], [2, 2], [3, 0], [3, 1], [4, 0]] got=[]), reported ['edge-case']
- longest-common-subsequence/match-extends-the-best-neighbour — planted bug (input=('aa', 'a') expected=1 got=2), reported ['complexity']

**False positives** (on code the oracle proved correct)

- group-anagrams/walkccc — complexity: Sorting each string to build the key gives O(n*k log k) where k is the max string length; the standard optimal approach uses a character-count tuple as the key to get O(n*k); bug: The function is annotated to return list[list[str]] but actually returns dict.values(), a view object rather than a list; while this often works because callers iterate over it, it doesn't match the declared return type and could break code that expects list-specific behavior (e.g., indexing, len checks in some harnesses)
- distinct-subsequences/canonical — complexity: The DP table is stored as a dictionary keyed by every (i, j) pair, giving O(n*m) space. Since each row only depends on the next row, this can be reduced to O(m) (or O(min(n,m))) space using a single rolling array, which is the standard optimal-space approach for this problem.
- distinct-subsequences/walkccc — complexity: The DP table is allocated as full (m+1) x (n+1) 2D array, using O(m*n) space, when the recurrence only depends on the previous row, so it can be rolled into a single O(n) array (or O(min(m,n)) with the shorter string as columns). This is asymptotically worse than the optimal space bound.
- valid-palindrome/canonical — complexity: The solution builds an entirely new filtered string and reverses it, using O(n) extra space, when the standard approach solves this with O(1) space via two pointers scanning from both ends; complexity: Repeated string concatenation with += inside the loop can degrade to O(n^2) time in the worst case since strings are immutable and each concatenation may create a new string
- valid-palindrome/aviv-13 — complexity (private code: the claim is in evals/cache)
- valid-palindrome/aviv-36 — complexity (private code: the claim is in evals/cache)
- house-robber-ii/canonical — complexity: nums[1:] and nums[:-1] each allocate a new list of size n-1, making total space usage O(n) instead of the O(1) extra space achievable by running the same rolling-variable loop over index ranges (e.g., helper(nums, 1, n-1) and helper(nums, 0, n-2)) without copying.
- pacific-atlantic-water-flow/canonical — edge-case: The dfs is implemented with plain Python recursion and no sys.setrecursionlimit adjustment. On a grid near the maximum constraint (up to 200x200 = 40,000 cells) with a monotonically increasing height arrangement (e.g., a snake-like path of strictly increasing values), the recursion can chain through most of the cells in a single call stack, exceeding Python's default recursion limit (1000) and raising a RecursionError even though the algorithm itself is logically correct.
- longest-common-subsequence/canonical — complexity: Uses a full (m+1) x (n+1) 2D array for space, i.e. O(m*n) space, when the recurrence only ever needs the current and next row, so it could be reduced to O(min(m,n)) with a rolling array.
- longest-common-subsequence/walkccc — complexity: The full 2D dp table of size (m+1)x(n+1) is kept, but the LCS length recurrence only ever needs the previous row (or column) to compute the next one. This means space is O(m*n) when it could be reduced to O(min(m,n)) with a rolling 1D array, which matters when m and n approach the constraint limit of 1000 each (dp table of ~1,000,000 ints).

