# Evals

How the coach measures its language model instead of trusting it: what is measured, the bank of
problems with labels proven by running code, the clean controls, the held-out split, and how to
run it without wasting money. Every run's numbers are in [evals/RESULTS.md](../evals/RESULTS.md),
append-only.

## Why measure, and what

"The feedback looked good" is not a claim to defend or iterate against. A language model writes
answers that sound right when they are not, a prompt change cannot be called an improvement
without a number to compare, and in the coach a wrong review costs something: an invented edge
case caps a correct solve's grade at 2 and brings it back in three days
([logic.md](logic.md#grading-an-attempt)). An eval runs the model over a fixed set of examples
whose right answer is known in advance and reports rates that can be compared across versions.

[evals/run_evals.py](../evals/run_evals.py) measures the three things the model does in the coach:

- **Feedback** (`--feedback`), the main one: does a review find real flaws, and does it invent
  them in correct code.
- **Enrichment** (`--enrichment`): does `intended_pattern` match the section NeetCode files the
  problem under in its published Blind 75 (97% of 29 problems on `enrich-v5`).
- **Retrieval** (`--retrieval`): is a problem known to be related in the top five results
  ([search.md](search.md)).

**Two numbers for feedback, because each alone is easy to game.** *Recall* is the share of
planted flaws a review reports; the *false-positive rate* is the share of proven-correct
solutions a review calls wrong. A reviewer that calls everything a bug has 100% recall, and one
that never says anything has no false positives. The second matters most in the coach, where a
false positive lowers a correct solve's grade.

On `bank-v5`'s held-out test split (32 problems the prompt was never tuned on), `review-v6` on
`claude-sonnet-5` reached **88% recall** (74/84, 95% Wilson interval 79-93%) and a **3%
false-positive rate** (2/59, 1-12%). The interval says how far a rate could move on the sample
size alone: when two versions' intervals overlap, neither can be called better. The coach now
sends `review-v7`, which added only the recursion rule ([llm.md](llm.md#reviewing-a-solve)) and
is not scored yet.

## The bank: one file per problem

[evals/bank/problems/](../evals/bank/problems/) holds one module per problem, 92 in all (60 in
`dev`, 32 in `test`). [two_sum.py](../evals/bank/problems/two_sum.py) shows every part:

- `CANONICAL`: the standard optimal solution (Two Sum's one-pass hash map), as a string, because
  it is run like pasted code and sent to the model as text. In `dev` it was written in this repo;
  in `test` it is the solution NeetCode published (`external_code("neetcode", NUMBER)`).
- `TESTS`: a handful of `(input, expected, kind)` rows, LeetCode's examples from the statement
  plus edge cases written here, each marked `general` (an ordinary input) or `edge` (a boundary).
  The kind is what later tells a bug from an edge case.
- `SCALE` and `SPACE_SCALE`: one large input each, to time a solution and to measure its peak
  memory.
- `reference`: a brute force (Two Sum's two nested loops, O(n²)), simple enough to check by
  reading. It is the answer key everything else is compared with.
- `generate(rng)`: random inputs the constraints allow. Two Sum's are short arrays of -9..9 with
  exactly one answer, small on purpose: duplicates and colliding sums, where bugs show, are
  common, and the brute force stays fast.
- `valid` (required in `test`): the problem's LeetCode Constraints section as code, written with
  the fetched statement open, never from memory (LeetCode changed Reverse Bits' constraints
  under an older copy).
- `MUTANTS`: the canonical with one deliberate change each (`nested-loop`,
  `insert-before-check`), and the kind of flaw its author aimed for (`intended`). Choosing what to
  break is authored; the label is not (below).
- `CLEAN_VARIANTS`: more correct solutions written here (`dev` only), each a
  `representative` control or a `regression` one (below).

**Which split a problem is in** is its `SPLIT` line, and everything filters on it (`--split`).
`bank-v5`'s test split was drawn, not chosen: problems in both pinned repos, free, not already in
the bank, shaped for the harness, none answered by mutating its input and none accepting several
answers; then within each difficulty, sorted by number, shuffled by `random.Random(20260929)`,
and the first 4 Easy, 18 Medium and 10 Hard taken. A drawn problem found unfit is replaced by the
next in its difficulty's order, never by choice, and the bank was committed (`908fada`) before any
review call on it. `bank-v4`'s test split, already seen, moved to `dev`.

## The oracle: every label comes from running code

[evals/bank/oracle.py](../evals/bank/oracle.py) gives each mutant its label by running it, never
by trusting what its author intended (`oracle.classify`):

- fails a `general` test: **bug**;
- fails only `edge` tests: **edge-case**;
- passes every test but is at least 5x slower than the canonical at `SCALE` (or times out):
  **complexity**;
- passes everything at the canonical's speed: an equivalent mutant, **discarded**. Weak tests
  then cost a fixture rather than producing a wrong label, the safe direction to fail.

`evals/validate_bank.py` reports a mutant whose executed label differs from its `intended`, and
the executed one is what is scored. `run_evals.build_bank` labels every mutant before any call,
sends only the code, and counts a flaw caught only when the review reports that exact category.

**"Proven" means checked against a brute force on a thousand inputs**, not a formal proof. The
chain is built bottom up, each step leaning on the one before:

1. Every input, test, `SCALE` and generated, passes `valid` (`verify_inputs`): a label earned on
   an input the problem excludes is no label.
2. Every hand-written test's expected answer equals the `reference`'s (`verify_canonical`), so a
   test with a wrong answer stops the bank.
3. The canonical passes every test and returns what the `reference` returns on 1,000 generated
   inputs, seeded by the problem number so every run judges the same ones. The reference's
   answers are computed once per problem and kept, since the brute force is slow.
4. A clean control must come out of `classify` as indistinguishable from the canonical, agree
   with the reference on those 1,000 inputs, and not need megabytes on `SPACE_SCALE` where the
   canonical needs almost nothing (`verify_clean`).

**Tests that are too weak fail loudly.** A mutant that passes every hand-written test but
disagrees with the reference on a generated input raises `TestsTooWeak` with that input;
likewise one that fails only edge tests but also an input the problem's `is_edge` does not call
an edge. Someone adds a test for the counterexample and decides whether it is general or edge;
the check is never loosened, and `validate_bank` must report none.

**What it does not prove.** A control is proven correct and no slower than the canonical, not
optimal, which is why a complexity remark on one is not counted as a false positive (below). And
a thousand small inputs are strong evidence, not certainty: `generate` is authored, and a bug
that shows only on an input it never makes would pass.

**Timing is the fastest call, never one call alone** (`time_at_scale`): a pause only adds time,
and a single pause once timed a clean control at 28x. A solution that finishes in microseconds is
called repeatedly until 0.05 s has accumulated.

## Clean controls, and what counts as a false positive

A clean control is correct code the reviewer should call correct. Each has an `origin`
([evals/bank/controls.py](../evals/bank/controls.py)): `authored` (a `CANONICAL` or
`CLEAN_VARIANT` written in this repo), `neetcode` or `walkccc` (copied unmodified from those
MIT-licensed repos at pinned commits, through `evals.bank.import_external fetch|judge`, licenses
in [THIRD_PARTY_NOTICES.md](../evals/bank/THIRD_PARTY_NOTICES.md)), or `aviv` (one of Aviv's own
clean solves, imported from a copy of the database by `evals.bank.import_private` into the
gitignored `evals/bank/private/`, because the repo is public). In the test split nothing
authored counts: whoever writes code here also tunes the prompt, and could write in a style it
favours without meaning to. Code from outside is never edited; `judge` rejects a solution that
breaks a rule and records why, and the only thing ever prepended is the imports LeetCode's own
environment provides (`PRELUDE`). A fetched solution identical in structure to the canonical is
rejected as "same code as the canonical", so it is not counted twice. The bank holds 230 clean
controls and 251 written mutants.

**A false positive is a claim that proven-correct code is wrong**: a `bug` or `edge-case` issue,
or a bare `needs-work` verdict, read through `assessment.correctness_finding`, the rule the coach
caps a grade by, so the eval and the coach cannot disagree on what "wrong" means. A complexity
remark on a control is counted apart and scored neither way: the oracle proves a control correct
and no slower than the canonical, not optimal, so it cannot call the remark false, and on
`bank-v4`'s test split 8 of the 10 "false positives" under the old definition were such remarks,
most of them right. "Any issue", the false-positive rate until 2026-09-29, is still reported, so
older runs stay comparable. The definition was committed (`bdf313b`) before `bank-v5` was scored:
by either one the prompts are level (`review-v4` 4% and 20%, `review-v6` 3% and 19%), and the
headline moved because the question did. The two are never folded back together to move it.

**Regression controls are scored apart.** A control marked `regression` was written after a run
had shown a false positive like it (Two Sum's `relies-on-guaranteed-answer` probes flagging an
input the constraints exclude). The prompt revised after reading that run is expected to do well
on it, so pooled with the representative controls it would flatter the headline rate. Being
authored, none is in the test split.

**Broken down by origin**, because a reviewer that goes easy on famous solutions it has seen in
training and hard on code it has not would show up only there. On `bank-v5`'s test split:
NeetCode 7% (2/30), walkccc 0% (0/29), too few to read anything into.

## Dev and test, and what the results taught

**`dev` is for tuning, `test` only for scoring.** On `dev` every miss and false positive is
shown, read, and written against. On `test` only the rates are reported: its misses and false
positives stay out of stdout and RESULTS.md, because reading them is how a prompt gets tuned to
them, and the next number on those problems would measure the tuning, not the prompt.
`--reveal-test` shows them, for free from the cache, and spends the split: a prompt written after
it needs new test problems. That is what happened to `bank-v4`'s test split, now in `dev`.
`bank-v5`'s is not spent; revealing it is Aviv's call.

**What the runs showed, in order** (details in RESULTS.md):

1. **Fixing the eval moved the number, not the prompt.** `review-v1` and `review-v2` tied at
   29/30. What took recall from 93% to 97% was three defects in the ground truth, each found
   because the model disagreed with a label and turned out to be right: inputs marked as edges
   that were ordinary (different-length strings to an anagram check), tests that broke the
   problem's own constraints (empty arrays where `1 <= length`), and a "clean" control that was
   not (it iterated `prices[1:]`, an O(n) copy, and the model was scored a false positive for
   saying so). Since then a miss in the report carries its execution evidence, so a
   disagreement can be adjudicated rather than counted.
2. **A model switch broke the false-positive rate, and the eval caught it.** On
   `claude-sonnet-5`, `review-v3` kept recall at 29/30 but went from 0/13 to 3/13 false
   positives ("an empty list raises IndexError" where the constraints exclude one, "O(n) is not
   optimal" for Climbing Stairs at `n <= 45`). Thirteen controls could not measure a fix (0/13
   still allows a true rate near 23%), so the bank grew to 35 first; the unchanged prompt scored
   4/35, and `review-v4`, adding one rule (judge against the problem's stated constraints),
   scored 0/35 with recall unchanged.
3. **A held-out split showed the tuned numbers do not transfer.** On 25 problems no prompt had
   been written against, the same prompt caught 82% of planted flaws and flagged 20% of correct
   solutions, against 0/35 on the tuned ones (Fisher exact p = 0.004): the prompt was overfitted
   to the problems it was tuned on. Eight of those ten claims were defensible complexity remarks,
   and the misses were the reviewer's: eight bugs failing one of LeetCode's own examples, each a
   small edit to a famous solution, drew no comment.
4. **The rate was narrowed to what the oracle can prove** (above), committed before the next
   split was scored. On `bank-v5`'s seeded test split `review-v6` reached 88% recall and 3% false
   positives, and by that definition `review-v4`'s 20% had been 4%.

The lessons kept: most early gains came from fixing the measurement, and a disagreement with the
model is sometimes a bug in the bank; a number on the problems a prompt was tuned on says nothing
about new ones; a definition is changed before its result is seen, and reported both ways.

## Running it without wasting money

An eval calls the real model: scoring `bank-v5`'s test split is 145 review calls, about $3.77.
Four things keep a run to what it must buy:

```bash
uv run python -m evals.validate_bank                        # prove every label and control, no API calls
uv run python -m evals.run_evals --all --dry-run            # count the calls and the cost first
uv run python -m evals.run_evals --feedback --split test    # the held-out split
uv run python -m evals.run_evals --feedback --split test --reveal-test   # free from the cache; spends the split
```

- **`validate_bank` first**: it runs only the oracle, so a broken bank (`TestsTooWeak`, a label
  that differs from its `intended`) shows before any review is bought.
- **`--dry-run` counts with the code that buys.** `CallCache.pending` is the one function both use,
  on the same keys. They used to be two readings of one question: the run compared
  digest-bearing keys while `--dry-run` subtracted lengths, so editing a fixture left `--dry-run`
  reporting 0 calls for a run that paid for several.
- **A cache keyed by what the answer depends on.** Answers live in `evals/cache/` (gitignored),
  one file per prompt version and model, each keyed by the fixture, a digest of its code and a
  digest of the statement it was sent with. A repeat run costs nothing; correcting a label
  re-scores for free; editing a fixture re-buys just that one; a reworded statement, or a run with
  and without statements, cannot collide. A failed call is not stored, so the next run retries it
  instead of scoring a hole. Statements are fetched from leetcode.com once (free) and cached, not
  committed: they are LeetCode's text, and the repo is public.
- **On a model the harness has not run before, buy one call first** and see it cached and scored.
  On 2026-09-19 the `/` in an OpenRouter model's name made the cache path a directory, the write
  crashed, and about 33 answers and a day's free quota were lost; the name is now flattened
  (`/` to `__`).

**The other two evals.** *Enrichment* tags the 50 solutions of
[evals/corpus.py](../evals/corpus.py) and checks each `intended_pattern` against an `accept` set
whose primary entry is the problem's section in NeetCode's published Blind 75, an external
taxonomy; alternates are added only where that section is coarser than our vocabulary ("Graphs"
covers `dfs`, `bfs`, `union-find`, `topological-sort`) or a problem has two canonical approaches,
each listed so a reader can disagree with it. *Retrieval* makes no API call: it builds cards from
the enrichment cache, embeds them and the raw code locally, and on the 21 hand-labelled pairs of
[evals/pairs.py](../evals/pairs.py), problems sharing a technique and not merely a topic, checks in
both directions whether each is in the other's top five.

**What is not scored yet.** The coach sends `review-v7` and tags with `enrich-v6`; the published
numbers are `review-v6`'s (feedback) and `enrich-v5`'s, on 29 solutions (enrichment and retrieval).
The corpus has since grown to 50. A dry-run on 2026-11-02 counted what scoring them would buy: 145
review calls (about $3.77) and 50 enrichment calls (about $1.30).

**Two details of the report.** A false-positive line quotes the model's claim, because on code
proven correct the claim is the part worth arguing with; on Aviv's own solves it could quote the
solution, so those lines keep only their categories and the words stay in the gitignored cache.
And the retrieval misses that remain cluster where the small corpus is dense, 1-D DP problems and
a graph/tree trio, with several labelled pairs competing for five slots.

The known limitations, "clean" measured against the canonical rather than the optimum, small
edge-case samples, a bank of plain-value problems, controls clustered on a few problems, and
mutations whose choice is authored though every label is executed, are listed in
[RESULTS.md](../evals/RESULTS.md#known-limitations).
