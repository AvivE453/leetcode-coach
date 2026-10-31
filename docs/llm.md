# The language model

Where the coach asks a language model for a judgement, how the answer becomes a checked object,
and what happens when the model cannot answer.

## Where the model is used, and where it is not

The model is called for two things only:

- **Tagging** ([coach/enrich.py](../coach/enrich.py)): after a solve is logged, the model names
  the patterns the code is built on and the problem's canonical approaches.
- **Reviewing** ([coach/review.py](../coach/review.py)): only on a click on the Solutions page,
  the model reads the code and reports bugs, edge cases and complexity.

Everything else (grades, the review schedule, mastery, approach practice, the Daily Plan, the
Weekly Review) is ordinary code over the history ([logic.md](logic.md)), because it has to be
fast, free and the same on every read. Opening a page never calls the model: a review is bought
on a click, stored in `reviews`, and reused until it is explicitly refreshed.

**One way in.** Both go through `llm.parse(prompt, output_format, ...)` in
[coach/llm.py](../coach/llm.py), which takes a prompt and a Pydantic class and returns a
validated instance of it, or raises `LLMUnavailable`. A caller never sees which provider
answered or any SDK's own exceptions.

**The solve is stored before the model is called, and the model is called outside the
transaction.** Logging a solve is two commits:

1. `service.log_solve` stores the solve and replays its schedule in `with conn:`. No model.
2. `service.tag_solution_now` calls the model first, then stores the tags (and discards the
   solve's vector) in a second `with conn:`.

So a model that fails, has no key, or is out of quota never loses a solve; `coach enrich` tags
it later. And the call, which can take seconds on Sonnet or minutes on a slow free model, never
runs while SQLite holds a write lock, which would make every other write wait for it. A call
that fails has written nothing, so there is nothing to roll back.

**Every answer records where it came from.** Each `enrichments` and `reviews` row stores the
model's name and the prompt's version (`PROMPT_VERSION`: `enrich-v6`, `review-v7`). When a
prompt changes, the rows written under the old one can be found and re-bought one call each
(`coach enrich --retag` re-tags everything; there is no partial re-tag yet), instead of every
row looking alike.

## Structured outputs

A model answers in text, and the code needs an object with fixed fields. So every call sends a
schema with the prompt and the provider holds the model to it: the answer is JSON that fits, and
the SDK parses it into an instance of a Pydantic class. The class is the schema; nothing is
written as JSON Schema by hand.

```python
class Enrichment(BaseModel):
    main_patterns: list[Pattern] = Field(min_length=1)
    intended_pattern: Pattern
    intended_secondary_patterns: list[Pattern]
    secondary_patterns: list[Pattern]
    data_structures: list[str]
    key_trick: str
    time_complexity: str
    space_complexity: str
```

**A controlled vocabulary, enforced as a type.** `Pattern` is a `Literal` of 28 names, which the
schema turns into an enum, so the model cannot invent one and tags never fragment into
`dp`/`DP`/`dynamic programming`. The rest of the code reads the same list as
`enrich.PATTERNS = get_args(Pattern)`. LeetCode's own tags are kept for the opposite job: they
are coarse enough to find new problems, while ours are fine enough to diagnose a weakness. The
price of an enum is that a missing pattern is not a missing tag but a wrong one: before
`bucket-sort` joined the list, an O(n) bucket-sort solve of Top K Frequent Elements, which its
review called optimal, could only be tagged `hashmap`, missed the problem's `heap`, and was sent
to approach practice. A solve flagged off-pattern that its review calls optimal is the sign to
look for.

**What the schema cannot say** goes in a `model_validator`, which runs after the fields are
checked. `Enrichment` drops repeated patterns (`dict.fromkeys` keeps the first of each, in order)
and removes a secondary pattern that is also a main one, because every main pattern gets the
solve's full score and a repeat would count one solve twice. `Review` uses `Literal`s the same
way for its verdict (`optimal`, `acceptable`, `needs-work`) and each issue's category (`bug`,
`edge-case`, `complexity`).

**Each provider enforces it its own way.** Anthropic takes `output_format=` and returns
`parsed_output`. OpenRouter takes `response_format=`, plus `provider.require_parameters`: it
routes a request to one of several providers, and one that ignored the schema would answer in
free text and fail every time, so the request may only go to a provider that honours every
parameter sent.

**An answer that does not fit** raises Pydantic's `ValidationError`, which `llm._complete` turns
into `LLMUnavailable` ("did not fit the expected schema (2 field error(s))"). It once escaped as
it was, out of a log request that had already saved the solve.

## Tagging a solve

[coach/enrich.py](../coach/enrich.py) asks the model to fill `Enrichment` for one solve. It has
two layers of tags, because "solved" and "learned" are different questions:

- **How this code works**: `main_patterns` and `secondary_patterns`, describing the approach as
  written, even when it is a brute force. The prompt insists on it: the tags "must describe HOW
  this specific solution works - not the problem's official topic labels".
- **What the problem teaches**: `intended_pattern`, the canonical optimal approach, and
  `intended_secondary_patterns`, other approaches a strong candidate could lead with and still
  have solved it properly ("judge the problem itself, not the code above").

If a brute-forced Maximum Subarray were filed under `dp-1d`, `dp-1d`'s mastery would rise on a
solve that never used it, and the plan would never schedule the one thing most needed. The
disagreement between the layers is the signal: it is what `enrich.off_pattern` reads, and what
opens approach practice ([logic.md](logic.md#approach-practice)).

Within the first layer, a main pattern is one the solution cannot be described without, and
several are equal: a memoized DFS computing a knapsack recurrence is both `dfs` and
`dp-knapsack`, and each gets the solve's full score. A secondary pattern is one the solution
leans on; it counts toward the off-pattern check but never toward mastery or the pattern table.
In the second layer, Best Time to Buy and Sell Stock is a one-pass `greedy` and a textbook
`dp-1d`, so solving it either way is solving it properly.

**The accepted set only grows.** The model does not name the same alternates every time, so
`enrich.save_intended` merges instead of replacing: `intended_pattern` takes the newest answer
(a previous central pattern is demoted into the alternates, not dropped), and the alternates
accumulate. Replacing let one forgetful answer narrow the set and re-flag a solve that had
legitimately used a dropped approach, sending it back to approach practice it had completed. It
returns the merged set as stored (`enrich.Canonical`), and a solve is judged against that, never
against the answer just received.

**Tag, persist, judge.** `service.tag_solution_now` is the one place that does all three: it
calls the model outside any transaction, then in one `with conn:` saves the tags, discards the
solve's vector (it was built from the old tags and would describe tags the solve no longer has)
and merges the accepted set, then judges the solve against what was stored. It returns two
signals off one set comparison, both free: `off_pattern`, the sharp one (no accepted approach
used), and `also_solvable_with` (`enrich.unused_canonical`), a note listing the accepted
approaches this solve did not use. The note is computed when a solve is shown, not frozen when
it was stored, so widening a problem's set later widens the note on old solves too.

**Backfill.** `enrich.to_tag` lists the solves with no `enrichments` row, and `coach enrich`
tags them, then rebuilds every missing vector. With `--retag` it lists every solve, which is how
a changed prompt reaches solves tagged before it, at one call each.

## Reviewing a solve

A review is bought only on a click on the Solutions page, through `service.review_solution_now`:

1. A stored review is returned as it is unless `refresh` was asked for: looking again is free
   and writes nothing.
2. `service.problem_content` supplies the problem statement (below).
3. `review.review_solution` calls the model, outside any transaction.
4. In one `with conn:`, the review is saved and the problem's schedule replayed, because a review
   re-grades the attempt it judges ([logic.md](logic.md#grading-an-attempt)). A review whose
   schedule did not follow would be a finding mastery counts and the planner ignores. Replaying
   after the call also counts any solve logged while the model was answering.

The answer is a `Review`: strengths, issues (each a `bug`, `edge-case` or `complexity` with a
description), the code's time and space complexity, the optimal time complexity, a better
approach or none, and a verdict (`optimal`, `acceptable`, `needs-work`). The issue categories
are what cap the grade.

**Most of the prompt is about not inventing problems**, and each rule came from one that was
invented:

- Issues are judged against the problem's stated constraints and guarantees: an input the
  constraints exclude is not a flaw, and relying on a guarantee is not a flaw. Reviews stored
  before `review-v4` may carry false "empty input" edge cases.
- The category is decided by the input that breaks the code: an ordinary input a reader would
  write down first is a `bug`, a boundary the constraints allow (empty, one element, all
  negative, integer limits) is an `edge-case`, and a boundary failure is never a `bug`.
  `complexity` is correct code with a worse complexity than the standard approach, and a faster
  algorithm that makes no difference at the allowed sizes does not count.
- Recursion is never an issue (`review-v7`): `review-v6` flagged recursion depth on a BST of up
  to 10^4 nodes as an edge case, though LeetCode runs it, and the cap at 2 lapsed a correct
  solve. An iterative rewrite is suggested only when it improves the complexity or the problem
  calls for it.
- A correct, optimal solution gets an empty issues list, and every strength must point at
  something visible in the code, never generic praise.

**The problem statement.** To judge against the constraints, the model has to see them.
`service.problem_content` fetches LeetCode's statement the first time a problem is reviewed
(one GraphQL call, `catalog.fetch_content`), flattens its HTML to text and stores it in
`problems.content`, so a problem never reviewed never costs a request. Paid-only problems have
none, because the public API withholds it (about a fifth of the catalog), answering 200 with
the field null, which is why a malformed answer reads as no statement rather than an error. A
failed fetch stores nothing, so it is tried again next time. Without a statement the prompt tells the model to use
what it knows of this problem's actual constraints, never a generic worst case. Both branches
run for real, so `review_solution`'s `content` has no default: a default once let the eval
harness score the no-statement branch without saying so, under the same version name as the
prompt the coach sends.

**32,000 tokens.** `review.MAX_TOKENS` is large because the model's thinking counts toward it.
Terse code whose correctness rests on an unexplained trick draws long thinking: three of
`bank-v5`'s 145 test reviews ran out at 16,000, and a cut-off answer is paid for and thrown away.

**How good it is** is measured by the evals, not assumed: `review-v6` caught 88% of the planted
flaws on held-out problems and called proven-correct code wrong 3% of the time
([evals/RESULTS.md](../evals/RESULTS.md)). `review-v7` added only the recursion rule and is not
scored yet.

## When the model cannot answer

A caller of `llm.parse` gets one of two things: a validated object, or `LLMUnavailable`. So each
caller catches one exception and degrades: `tag_solution_now` and `review_solution_now` return
a result marked `skipped` with the reason, the page shows it, and the solve, stored before the
call, stays. `coach enrich` tags what was skipped.

**One translator.** `llm._complete` wraps every call. It raises at once when the model's key is
missing, then turns each SDK failure into `LLMUnavailable` with a sentence: a rate limit
(OpenRouter's free daily cap gets its own, because its raw message carries the user id), any
other HTTP status, no connection, a truncated answer, an answer that does not fit the schema,
and finally each SDK's base error class, so a rarer failure degrades instead of crashing. Each
handler takes the pair of exceptions, one per SDK, which name their errors alike, and the rate
limit comes before the status error it subclasses. Programming errors (`TypeError`,
`AttributeError`) are deliberately not caught: they are bugs here, not the API degrading, and
must stay loud.

**Failures that do not look like errors.**

- Anthropic: an answer that stopped on `refusal` or `max_tokens` is not an answer. The stream
  parses the JSON before it reports why it stopped, and structured output is valid JSON unless
  it was cut off, so a `json_invalid` validation error is read as truncation.
- OpenRouter answers HTTP 200 for failures too: an `error` in place of the choices (an
  overloaded provider, say), or an `error` inside a choice that finished with `"error"`, which
  can still carry content that fits the schema and would pass the failure off as the model's
  answer. `llm._openrouter_message` checks the body before the SDK parses it, also because the
  SDK meets a malformed body (no JSON, no choices) with a `TypeError` or `IndexError` that would
  escape as a bug and 500 a request whose solve is already saved. Its tests run the real SDK
  over a mock transport (`openrouter_answering` in `tests/test_llm.py`), never a fake that hands
  back a parsed choice, because the bugs live in exactly that step.

**A time budget.** `CALL_TIMEOUT` is 180 s and `CALL_RETRIES` 1, so a stuck call holds the
request for six minutes at most, where the SDKs' defaults (600 s a try, two retries) would hold
it for half an hour. The slowest answer seen, a free model tagging a solve, took about two
minutes. Anthropic calls stream, so there the timeout bounds a silence, not the whole answer: a
review can run as long as its tokens take.

## Two providers, picked by the model's name

Two APIs are supported: Anthropic's own, and OpenRouter, which serves many vendors' models,
free ones among them, behind one key. Which one a call goes to is read off the model's name
(`llm.on_openrouter`): OpenRouter's are all `vendor/model`, Anthropic's have no slash. So
switching is one `COACH_MODEL` line in `.env`, and only the key that model needs is read
(`llm.key_name`): someone on a free model needs no Anthropic key at all.

The name lives in [coach/config.py](../coach/config.py): `MODEL` defaults to `claude-sonnet-5`,
the model the eval numbers were measured on, and `COACH_MODEL` overrides it (`config.load_env`
reads `.env` with `setdefault`, so a real environment variable wins). `EVAL_MODEL` is separate,
so the coach can run on one model while the evals score another. The default used to be a free
OpenRouter model, until OpenRouter withdrew its free endpoint (2026-09-30); free models come
and go, so `.env.example` lists a few as comments instead of the code naming one, and none is
scored.

**No fallback from one to the other.** OpenRouter's free tier is 50 requests a day across all
free models; a fallback would quietly start billing a paid model the day it ran out, and that
day's solves would be tagged by a model nobody chose. A failure stays an `LLMUnavailable`, and
every enrichment and review stores the model that wrote it, so a history tagged by two models
stays readable.

The two SDK clients are created once and kept (`llm.anthropic_client`, `llm.openrouter_client`),
with the time budget above. Anthropic's sends an `anthropic-workspace-id` header when
`ANTHROPIC_WORKSPACE_ID` is set, because an identity-linked key must name the workspace it acts
in.
