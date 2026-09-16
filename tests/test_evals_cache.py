"""The eval runner's cache: what has been paid for, and what a run still owes.

`--dry-run` exists to answer "how much will this cost" before the money is spent,
and it used to answer it a different way than the run itself did - comparing
lengths where the run compared digest-bearing keys. Editing a fixture (the exact
thing the digest is for) then left --dry-run reporting 0 calls for a run that
paid for several, in the direction that costs money rather than the one that
merely annoys.

So the invariant these tests hold down is not "pending() looks right" but
`fill()` calls for exactly what `pending()` named. No API calls and no execution
oracle here: items are hand-built pairs and the worker is a recorder.
"""

import json

import pytest

from evals import run_evals


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setattr(run_evals, "CACHE_DIR", tmp_path / "cache")
    return run_evals.CallCache("reviews", "review-v9", "test-model")


def item(name, code, statement=None):
    """The shape both key functions read: a slug/id pair and the code they scored."""
    return {"slug": name, "id": "canonical", "code": code, "statement": statement}


def keyed(*items):
    return [(run_evals.review_key(i, i["statement"]), i) for i in items]


def recorder(answer="ok"):
    """A stand-in for the API call, remembering what it was asked to buy."""
    called = []

    def run_one(entry):
        called.append(entry["slug"])
        return run_evals.review_key(entry, entry["statement"]), answer

    return run_one, called


def test_pending_is_exactly_what_is_not_cached(cache):
    pairs = keyed(item("a", "code-a"), item("b", "code-b"))
    assert len(cache.pending(pairs)) == 2, "an empty cache owes every call"

    run_one, _ = recorder()
    cache.fill(pairs[:1], run_one, "buying")

    assert [i["slug"] for i in cache.pending(pairs)] == ["b"]


def test_a_stale_entry_does_not_hide_a_call_the_run_will_make(cache):
    """The regression: same fixture, edited code, an answer bought for the old one.

    The cache still holds an entry for this slug - a count of entries would say
    everything is paid for - but it answers a question about code that no longer
    exists, so the run has to buy it again and --dry-run has to say so.
    """
    run_one, called = recorder()
    cache.fill(keyed(item("a", "original")), run_one, "buying")
    assert called == ["a"]

    edited = keyed(item("a", "edited"))
    assert len(cache.load()) == 1, "the answer for the old code is still on disk"
    assert [i["slug"] for i in cache.pending(edited)] == ["a"]


def test_fill_calls_for_exactly_what_pending_named(cache):
    """The invariant that makes --dry-run's number the run's number.

    Both sides of the comparison come from the same call, so this fails if either
    one starts deciding for itself what counts as already bought.
    """
    run_one, _ = recorder()
    cache.fill(keyed(item("a", "code-a")), run_one, "buying")

    pairs = keyed(item("a", "code-a"), item("b", "code-b"), item("c", "code-c"))
    expected = [i["slug"] for i in cache.pending(pairs)]

    run_one, called = recorder()
    answers = cache.fill(pairs, run_one, "buying")

    assert called == expected == ["b", "c"]
    assert len(answers) == 3, "the cached one is returned alongside the two just bought"


def test_refresh_rebuys_everything(cache):
    run_one, _ = recorder()
    cache.fill(keyed(item("a", "code-a")), run_one, "buying")

    pairs = keyed(item("a", "code-a"))
    run_one, called = recorder()
    cache.fill(pairs, run_one, "buying", refresh=True)

    assert called == ["a"]
    assert len(cache.pending(pairs, refresh=True)) == 1


def test_a_failed_call_is_not_cached(cache):
    """A None answer is a degraded call, not an answer - the next run must retry it."""
    pairs = keyed(item("a", "code-a"))
    failing, _ = recorder(answer=None)
    cache.fill(pairs, failing, "buying")

    assert cache.load() == {}
    assert len(cache.pending(pairs)) == 1


def test_the_path_names_the_prompt_version_and_model(tmp_path, monkeypatch):
    """A prompt change must miss the old file rather than score against it."""
    monkeypatch.setattr(run_evals, "CACHE_DIR", tmp_path)
    v9 = run_evals.CallCache("reviews", "review-v9", "test-model")
    v10 = run_evals.CallCache("reviews", "review-v10", "test-model")
    other = run_evals.CallCache("reviews", "review-v9", "other-model")

    run_one, _ = recorder()
    v9.fill(keyed(item("a", "code-a")), run_one, "buying")

    assert v9.path.name == "reviews-review-v9-test-model.json"
    assert v10.load() == {} and other.load() == {}
    assert len(v10.pending(keyed(item("a", "code-a")))) == 1


def test_both_evals_key_by_the_code_they_scored():
    """Reviews always did; enrichment gained it here, and the retrieval eval needs it
    - it builds a card from a cached pattern beside the current code."""
    entry = run_evals.corpus.Entry(
        slug="two-sum", number=1, title="Two Sum", difficulty="Easy",
        official_tags='["array"]', code="original", accept=("hashmap",),
    )
    edited = run_evals.corpus.Entry(**{**vars(entry), "code": "edited"})

    assert run_evals.enrich_key(entry) != run_evals.enrich_key(edited)
    assert run_evals.enrich_key(entry).startswith("two-sum@")
    assert run_evals.review_key(item("a", "x"), None) != run_evals.review_key(item("a", "y"), None)


def test_the_statement_is_part_of_the_key(cache):
    """It is part of the prompt, so an answer bought under one must not be served for another.

    Two ways this matters: LeetCode rewords a statement and the stale answer has to
    miss, and a with/without pair of runs has to stay two measurements rather than
    silently becoming one.
    """
    with_statement = item("a", "code-a", "1 <= n <= 10^4")
    without = item("a", "code-a")
    reworded = item("a", "code-a", "1 <= n <= 10^5")

    keys = {run_evals.review_key(i, i["statement"]) for i in (with_statement, without, reworded)}

    assert len(keys) == 3
    run_one, _ = recorder()
    cache.fill(keyed(with_statement), run_one, "buying")
    assert [i["slug"] for i in cache.pending(keyed(without))] == ["a"]


def test_a_run_refuses_rather_than_mixing_statemented_and_bare_fixtures(monkeypatch):
    """Half a bank scoring one prompt and half the other is a number describing neither."""
    monkeypatch.setattr(run_evals, "statements", lambda slugs, refresh: {"a": "1 <= n <= 10"})
    fixtures = [item("a", "code-a"), item("b", "code-b")]

    with pytest.raises(run_evals.MissingStatements) as caught:
        run_evals.bank_statements(fixtures, refresh=False)

    assert caught.value.args[0] == ["b"], "it names what is missing, before any money moves"


def test_the_report_heading_says_which_branch_it_measured():
    """One prompt version, two prompts - paid-only problems get no statement.

    Two tables both headed `review-v5` and disagreeing is the confusion this whole
    change exists to remove, so the variant is not optional in the heading.
    """
    scores = run_evals.score_feedback([control_fixture()], [{"issues": [], "verdict": "optimal"}])

    with_text = "\n".join(run_evals.feedback_lines(
        {"prompt_version": "review-v9", "statements": True, "splits": scores}))
    without = "\n".join(run_evals.feedback_lines(
        {"prompt_version": "review-v9", "statements": False, "splits": scores}))

    assert "(with problem statements)" in with_text
    assert "(without problem statements)" in without


def control_fixture():
    return {"slug": "two-sum", "id": "canonical", "category": None, "split": "dev",
            "control": "representative", "origin": "authored", "code": "..."}


def test_the_cache_file_stays_readable_json(cache):
    run_one, _ = recorder()
    cache.fill(keyed(item("b", "code-b"), item("a", "code-a")), run_one, "buying")

    on_disk = json.loads(cache.path.read_text())
    assert sorted(on_disk) == list(on_disk), "written sorted, so diffs stay reviewable"
    assert len(on_disk) == 2
