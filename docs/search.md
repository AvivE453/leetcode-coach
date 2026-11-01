# Semantic search

How the coach finds past solves similar to a new one: what is embedded, how a match is scored,
why each solve has its own vector, and where it is used.

## An embedded card, not raw code

An embedding model turns a text into a vector of numbers, trained so that texts with similar
meaning land close together even when they share no words. The coach uses a small local one,
`all-MiniLM-L6-v2` from `sentence-transformers` (`config.EMBED_MODEL`), unrelated to the language
model of [llm.md](llm.md): no key, no cost, no quota. `embed.encode` loads it once and keeps it,
and returns unit-length `float32` vectors (`normalize_embeddings=True`), which makes scoring a
match a dot product (below).

What is embedded is a card, not the code alone ([coach/embed.py](../coach/embed.py),
`card_text`):

```text
Two Sum
pattern: hashmap
trick: store each number's index and look up target - x in one pass

def twoSum(self, nums, target): ...
```

Two solves of the same technique can look nothing alike as code, and a small model reads mostly
the words. With the main patterns and the key trick from tagging written into the card, the
shared technique is in words, so two problems that share a technique retrieve each other even
when their code shares no vocabulary. Measured, not assumed: on pairs of problems known to be
related, the related one is in the top five (recall@5) 79% of the time with cards and 62% with
raw code, on `enrich-v5`, up from a 5-point gap on `enrich-v2`. That is one run on 42 pair
directions, so read it as a clear direction more than a precise size.

The price is that a vector depends on its solve's tags: a card names the main patterns, so a
re-tag makes the old vector describe tags the solve no longer has (see below).

## Scoring a match, without a vector database

A vector is stored in `embeddings` as a `float32` blob (`vector.tobytes()`, 4 bytes per number)
and read back with `np.frombuffer`, which copies nothing. Similarity is cosine similarity, and
because every vector is unit length, the cosine is just the dot product.

`embed.search(conn, queries, top_k, exclude_problem, patterns)` reads every stored vector and
scores it:

- `queries` is a matrix, one row per asking vector, and a stored solve scores its best dot
  product against any of them (`np.max(queries @ vector)`).
- `exclude_problem` leaves out the problem being asked about.
- `patterns`, when given, keeps only solves sharing at least one of those main patterns, so the
  embedding ranks within them instead of across every pattern, and an unrelated pattern never
  wins just for being the least-bad match. The log page's neighbors pass the new solve's main
  patterns; `coach similar` passes none.
- Each problem is represented by its best-scoring solve (the latest on a tie), so a problem
  appears once, and the results are the best `top_k` by score.

**No vector database.** It is a brute-force loop over every vector, in numpy, on every search.
At a few hundred solves that takes microseconds; a vector database would be infrastructure to
install, back up and keep in step, bought for a problem this project does not have. Keeping the
vectors in SQLite also means deleting a solve deletes its vector in the same transaction. It
would start to matter at hundreds of thousands of vectors.

## One vector per solve, never one per problem

`embeddings` is keyed by `solution_id` (Aviv's call). Re-solving a problem a different way, Best
Time to Buy and Sell Stock as `greedy` and then as `dp-1d`, embeds a new card for the new solve
and leaves the old one untouched, so the problem has two vectors and is found through either
approach: a `greedy` query reaches it through the greedy solve, a `dp-1d` query through the DP
one. One vector per problem, the latest solve's or an average of all of them, would leave it
findable through one approach at most (an average sits between the approaches, near neither),
which throws away exactly the variety re-solving a problem a new way is meant to build.

Both sides of a search follow the solve:

- **The answer.** A hit (`embed.Hit`) names the solve that matched, and
  `service.neighbor_details` describes the neighbor by that solve's patterns and key trick.
  Describing it by the problem's latest solve labelled a match found through the DP solve as
  greedy.
- **The question.** `coach similar <number>` asks with every solve of the problem, so a problem
  solved both ways finds the relatives of both approaches, not only the latest one's.

**A vector never outlives the tags it describes.** A stored vector changes only when its own
solve is re-tagged. The card names the solve's main patterns, so `service.tag_solution_now`
discards the vector in the new tags' own commit; the log page embeds the solve again right
after tagging (`service.enrich_solution_now`), and any `coach enrich` rebuilds every tagged solve
with no vector (`embed.to_embed`). The rebuild used to be the re-tag's own job, and a re-tag
whose embedding failed left the old vector searchable under the new tags, where a plain
`coach enrich`, looking only for solves with no vector, never found it. A missing vector is a
state that repairs itself; a stale one was not. Deleting a solve deletes its vector with it.

## Where it is used, and when the local model is missing

**Neighbors on the log page.** Logging a solve runs `service.enrich_solution_now`: it tags the
solve, builds its card from the new tags, embeds and stores it, and searches for the three
closest solved problems sharing one of its main patterns, excluding its own problem. The log
result lists them under "Similar solved problems", each described by the solve that matched.

**`coach similar`**, one of the three CLI commands kept because it has no page:

- `coach similar <number>` asks with every solve of a solved problem.
- `coach similar --paste` takes the statement of a problem not solved yet. A bare statement
  looks nothing like a stored card, so it first asks the language model to predict an optimal
  solution's pattern and key trick (`enrich.hypothesize`, HyDE-style: search with a hypothetical
  answer, not the question) and embeds them above the statement in the card's own format. If the
  model is unavailable, it matches on the raw statement and says so.

**When the local model is missing.** `sentence-transformers` lives in the optional `embed` extra
(`uv sync --extra embed`) because it pulls in `torch`. Without it, or when the model cannot be
downloaded or its cached copy is missing or corrupt (an `OSError`), `embed.encode` raises
`EmbeddingsUnavailable`. Only a failed load is that; an error from encoding itself stays loud.
Logging degrades in two steps: no language-model key means `skipped` (no tags, so no card), and
no embedding model means `embed_skipped` (tags saved, no vector or neighbors). Either way the
solve is stored, and `coach enrich` fills in the tags and then the vectors.

**Changing `EMBED_MODEL` invalidates every vector.** Vectors from two models live in different
spaces, and search would compare them without a word if their lengths matched. After a change,
empty `embeddings` and run `coach enrich`, which rebuilds every missing vector locally, with no
API calls.
