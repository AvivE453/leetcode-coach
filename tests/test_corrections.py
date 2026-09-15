"""Approach practice: what a problem still owes after a solve that used the wrong approach.

The pure tests build history.Attempts by hand, with the outcome and the review that grade
them, exactly as history.load() builds one from a stored row. The database tests go through
that loader, so a read of the wrong column cannot hide behind the pure half.
"""

import json
from dataclasses import replace
from datetime import date, timedelta

import pytest
from conftest import tag_solution

from coach import corrections, db, enrich, history

D1 = date(2026, 9, 12)
D2 = date(2026, 9, 15)
INTERVAL = timedelta(days=corrections.CORRECTION_INTERVAL_DAYS)

PROBLEM = {
    "number": 121,
    "slug": "best-time-to-buy-and-sell-stock",
    "title": "Best Time to Buy and Sell Stock",
    "difficulty": "Easy",
}
CANONICAL = enrich.Canonical("dp-1d", ["greedy"])
DP = ["dp-1d"]
BRUTE = ["math"]  # tagged, and none of the accepted approaches

BUG = ("needs-work", ("bug",))
EDGE = ("needs-work", ("edge-case",))
NEEDS_WORK = ("needs-work", ())
COMPLEXITY = ("acceptable", ("complexity",))


def issues(*categories):
    return [{"category": c, "description": "..."} for c in categories]


def problem_record(canonical=CANONICAL):
    return history.Problem(**PROBLEM, canonical=canonical)


def attempt(attempt_id, day, outcome="clean", main=None, secondary=(), review=None):
    """One attempt as the loader builds it. `main=None` is a solve not tagged yet."""
    verdict, found = review or (None, ())
    return history.Attempt(
        id=attempt_id,
        problem=problem_record(),
        day=day,
        outcome=outcome,
        minutes=None,
        main_patterns=None if main is None else tuple(main),
        secondary_patterns=tuple(secondary),
        verdict=verdict,
        issues=tuple(issues(*found)),
    )


def evaluate(*attempts, canonical=CANONICAL):
    """Judge one problem's attempts, each carrying `canonical` as the loader hands it over."""
    carried = [replace(a, problem=problem_record(canonical)) for a in attempts]
    return corrections.evaluate(PROBLEM, canonical, carried)


def reason(result):
    return None if result is None else result.reason


def owed_after_brute_force(*second_day):
    """A clean wrong-approach solve on D1, then `second_day`'s (outcome, main, review) on D2."""
    attempts = [attempt(1, D1, main=BRUTE)]
    for attempt_id, (outcome, main, review) in enumerate(second_day, start=2):
        attempts.append(attempt(attempt_id, D2, outcome, main, review=review))
    return evaluate(*attempts)


@pytest.mark.parametrize(
    "second_day, expected",
    [
        pytest.param([("clean", DP, None)], None, id="accepted-clean"),
        pytest.param([("struggled", DP, None)], None, id="accepted-struggled"),
        pytest.param([("hints", DP, None)], "assisted", id="accepted-hints"),
        pytest.param([("failed", DP, None)], "failed", id="accepted-failed"),
        pytest.param([("clean", BRUTE, None)], "wrong-approach", id="clean-with-no-accepted-approach"),
        pytest.param([("clean", DP, BUG)], "review-finding", id="accepted-clean-review-reports-a-bug"),
        pytest.param([("clean", DP, EDGE)], "review-finding", id="accepted-clean-review-reports-an-edge-case"),
        pytest.param([("clean", DP, NEEDS_WORK)], "review-finding", id="accepted-clean-review-says-needs-work"),
        pytest.param([("clean", DP, COMPLEXITY)], None, id="accepted-clean-review-reports-only-complexity"),
        pytest.param(
            [("failed", DP, None), ("clean", DP, None)], "failed", id="failure-then-clean-the-same-day"
        ),
        pytest.param([("clean", None, None)], "wrong-approach", id="success-not-tagged-yet"),
    ],
)
def test_what_completes_approach_practice(second_day, expected):
    """Aviv's completion table. None means nothing is owed any more; otherwise, why it still is."""
    assert reason(owed_after_brute_force(*second_day)) == expected


def test_nothing_is_owed_without_evidence_of_the_wrong_approach():
    """Failing with the accepted approach is ordinary SM-2 practice: a missing success says
    nothing about the approach. Neither does a solve never tagged, nor a problem whose
    canonical set was never stored."""
    assert evaluate(attempt(1, D1, "failed", DP), attempt(2, D2, "hints", DP)) is None
    assert evaluate(attempt(1, D1, "failed")) is None
    assert evaluate(attempt(1, D1, main=BRUTE), canonical=enrich.Canonical(None, [])) is None
    assert evaluate() is None


@pytest.mark.parametrize("dp_day, expected", [(D1, "wrong-approach"), (D2, "failed")])
def test_a_failed_accepted_solve_and_a_clean_wrong_one_never_add_up(dp_day, expected):
    """The accepted tags and the success must belong to one attempt: a failed DP solve plus a
    clean brute force is not "solved with DP", on separate days or on the same one."""
    result = evaluate(attempt(1, dp_day, "failed", DP), attempt(2, D2, "clean", BRUTE))

    assert reason(result) == expected


@pytest.mark.parametrize(
    "main, secondary",
    [(["dp-1d"], ()), (["greedy"], ()), (["math", "greedy"], ()), (["math"], ["greedy"])],
    ids=["central", "alternate", "alternate-as-a-second-main-pattern", "alternate-as-a-secondary"],
)
def test_any_accepted_approach_completes_it(main, secondary):
    assert evaluate(attempt(1, D1, main=BRUTE), attempt(2, D2, main=main, secondary=secondary)) is None


def test_a_success_before_the_wrong_approach_keeps_it_closed():
    """The requirement is to have shown an accepted approach once. Brute-forcing the problem
    again afterwards is an experiment, and forgetting the approach is SM-2's business."""
    assert evaluate(attempt(1, D1, main=DP), attempt(2, D2, "failed", BRUTE)) is None


@pytest.mark.parametrize(
    "same_day, expected",
    [
        ([("hints", DP, None), ("failed", DP, None)], "failed"),
        ([("clean", DP, BUG), ("hints", DP, None)], "assisted"),
        ([("clean", DP, EDGE), ("struggled", DP, None)], "review-finding"),
    ],
)
def test_a_failure_day_is_explained_by_its_outcomes_before_its_reviews(same_day, expected):
    assert reason(owed_after_brute_force(*same_day)) == expected


def test_a_correction_carries_its_problem_and_the_approaches_that_would_complete_it():
    result = evaluate(attempt(1, D1, main=BRUTE))

    assert result.problem == PROBLEM
    assert result.accepted == ["dp-1d", "greedy"]
    assert (result.latest_attempt, result.due) == (date(2026, 9, 12), date(2026, 9, 15))
    assert result.evidence == (1,)


def test_the_reason_and_evidence_describe_the_latest_tagged_day():
    """An untagged solve moves the due date - it was practice - but says nothing about the
    approach, so the reason still describes the last day that did."""
    later = D2 + timedelta(days=2)
    result = evaluate(
        attempt(1, D1, main=BRUTE),
        attempt(2, D2, "failed", BRUTE),
        attempt(3, D2, "clean", DP),
        attempt(4, later, "clean"),
    )

    assert (result.reason, result.evidence) == ("failed", (2, 3))
    assert (result.latest_attempt, result.due) == (later, later + INTERVAL)


def test_the_worked_example_from_sept_12_to_sept_18():
    """Each step re-reads the whole history, as every page load does, and each attempt that
    leaves the problem still owing restarts its three days."""
    history = [attempt(1, date(2026, 9, 12), main=BRUTE)]

    def due_and_reason():
        result = evaluate(*history)
        return result.due, result.reason

    assert due_and_reason() == (date(2026, 9, 15), "wrong-approach")

    history.append(attempt(2, date(2026, 9, 15), "failed", DP))
    assert due_and_reason() == (date(2026, 9, 18), "failed")

    # corrected straight after failing: the day still holds the failure
    history.append(attempt(3, date(2026, 9, 15), "clean", DP))
    assert due_and_reason() == (date(2026, 9, 18), "failed")

    history.append(attempt(4, date(2026, 9, 18), "clean", DP))
    assert evaluate(*history) is None


# ---------- through the database ----------


def make_db(tmp_path):
    conn = db.connect(tmp_path / "test.db")
    db.init_schema(conn)
    conn.executemany(
        "INSERT INTO problems (number, slug, title, difficulty) VALUES (?, ?, ?, 'Easy')",
        [
            (53, "maximum-subarray", "Maximum Subarray"),
            (70, "climbing-stairs", "Climbing Stairs"),
            (121, "best-time-to-buy-and-sell-stock", "Best Time to Buy and Sell Stock"),
        ],
    )
    return conn


def solve(conn, number, day, outcome="clean", main=(), secondary=(), review=None):
    """Store one attempt and its solution, tagged when `main` is given. Returns both ids."""
    attempt_id = conn.execute(
        "INSERT INTO attempts (problem_number, date, outcome) VALUES (?, ?, ?)",
        (number, day.isoformat(), outcome),
    ).lastrowid
    solution_id = conn.execute(
        "INSERT INTO solutions (problem_number, attempt_id, code, created_at) VALUES (?, ?, 'c', ?)",
        (number, attempt_id, day.isoformat()),
    ).lastrowid
    if main:
        tag_solution(conn, solution_id, *main, secondary=secondary)
    if review:
        store_review(conn, solution_id, review)
    return attempt_id, solution_id


def store_review(conn, solution_id, review):
    """Save a solve's review, replacing any stored one - as the Re-run button does."""
    verdict, found = review
    conn.execute(
        "INSERT OR REPLACE INTO reviews (solution_id, verdict, issues, created_at) VALUES (?, ?, ?, ?)",
        (solution_id, verdict, json.dumps(issues(*found)), D2.isoformat()),
    )


def owed(conn):
    return [(c.problem["number"], c.reason, c.due) for c in corrections.outstanding(conn)]


def test_load_reads_each_attempt_with_its_tags_and_review_oldest_first(tmp_path):
    conn = make_db(tmp_path)
    enrich.save_intended(conn, 121, "dp-1d", ["greedy"])
    enrich.save_intended(conn, 70, "dp-1d")  # a canonical set, but never attempted
    later, _ = solve(conn, 121, D2, main=DP, secondary=["greedy"], review=BUG)
    earlier, _ = solve(conn, 121, D1, "struggled")

    [loaded] = corrections.load(conn)

    assert loaded.problem["title"] == "Best Time to Buy and Sell Stock"
    assert loaded.canonical == ("dp-1d", ["greedy"])
    assert loaded.attempts == [
        attempt(earlier, D1, "struggled"),
        attempt(later, D2, main=DP, secondary=["greedy"], review=BUG),
    ]
    assert corrections.load(conn, 70) == []


def test_outstanding_reads_the_store_the_way_evaluate_reads_attempts(tmp_path):
    conn = make_db(tmp_path)
    enrich.save_intended(conn, 121, "dp-1d", ["greedy"])
    enrich.save_intended(conn, 70, "dp-1d")
    solve(conn, 121, D1, main=BRUTE)
    bugged, _ = solve(conn, 121, D2, main=DP, review=BUG)
    solve(conn, 70, D1, "failed", main=DP)  # failed with the accepted approach: ordinary SM-2

    [correction] = corrections.outstanding(conn)

    assert correction.problem["number"] == 121
    assert (correction.accepted, correction.reason, correction.evidence) == (
        ["dp-1d", "greedy"],
        "review-finding",
        (bugged,),
    )
    assert (correction.latest_attempt, correction.due) == (D2, D2 + INTERVAL)


def test_a_solution_without_an_attempt_owes_nothing(tmp_path):
    """Only a logged attempt is a dated practice event, so a stored solution with no attempt
    is neither evidence of the wrong approach nor a success."""
    conn = make_db(tmp_path)
    enrich.save_intended(conn, 121, "dp-1d")
    solution_id = conn.execute(
        "INSERT INTO solutions (problem_number, code, created_at) VALUES (121, 'c', ?)",
        (D1.isoformat(),),
    ).lastrowid
    tag_solution(conn, solution_id, *BRUTE)

    assert corrections.outstanding(conn) == []


def test_a_review_can_reopen_it_and_a_refreshed_one_close_it_again(tmp_path):
    """Revised evidence counts on the next read. Reopened, it is due three days after the
    practice itself - usually past by the time a review is read - so it is owed at once."""
    conn = make_db(tmp_path)
    enrich.save_intended(conn, 121, "dp-1d")
    solve(conn, 121, D1, main=BRUTE)
    _, dp_solve = solve(conn, 121, D2, main=DP)
    assert owed(conn) == []

    store_review(conn, dp_solve, BUG)
    assert owed(conn) == [(121, "review-finding", D2 + INTERVAL)]

    store_review(conn, dp_solve, ("optimal", ()))
    assert owed(conn) == []


def test_another_qualifying_solve_keeps_it_closed_when_one_is_found_buggy(tmp_path):
    conn = make_db(tmp_path)
    enrich.save_intended(conn, 121, "dp-1d", ["greedy"])
    solve(conn, 121, D1, main=BRUTE)
    _, dp_solve = solve(conn, 121, D2, main=DP)
    solve(conn, 121, D2 + timedelta(days=1), main=["greedy"])

    store_review(conn, dp_solve, BUG)

    assert owed(conn) == []


def test_the_stored_accepted_set_can_widen_but_never_narrows(tmp_path):
    """Widening the set completes a solve already stored. A later answer that forgets that
    approach reopens nothing, because save_intended accumulates and this reads what it stored."""
    conn = make_db(tmp_path)
    enrich.save_intended(conn, 121, "dp-1d")
    solve(conn, 121, D1, main=BRUTE)
    solve(conn, 121, D2, main=["greedy"])
    assert owed(conn) == [(121, "wrong-approach", D2 + INTERVAL)]

    enrich.save_intended(conn, 121, "dp-1d", ["greedy"])
    assert owed(conn) == []

    enrich.save_intended(conn, 121, "dp-1d", [])
    assert owed(conn) == []


@pytest.mark.parametrize(
    "tags, expected",
    [(DP, []), (BRUTE, [(121, "wrong-approach", D2 + INTERVAL)])],
    ids=["tagged-as-an-accepted-approach", "tagged-as-the-wrong-approach"],
)
def test_a_late_tag_judges_the_attempt_on_the_day_it_was_logged(tmp_path, tags, expected):
    """A solve logged with no API key waits, untagged, for `coach enrich`. Tagged days later,
    it counts for the day it was practiced: as a success, or keeping the date it already set."""
    conn = make_db(tmp_path)
    enrich.save_intended(conn, 121, "dp-1d")
    solve(conn, 121, D1, main=BRUTE)
    _, pending = solve(conn, 121, D2)
    assert owed(conn) == [(121, "wrong-approach", D2 + INTERVAL)]

    tag_solution(conn, pending, *tags)

    assert owed(conn) == expected


def test_owed_judges_each_problem_on_its_own_attempts():
    """The pure half of outstanding(): one flat history in, the problems still owing out,
    soonest due first - not in the order their attempts happened to be read."""
    stairs = replace(problem_record(), number=70, slug="climbing-stairs", title="Climbing Stairs")
    practised_later = replace(attempt(1, D2, main=BRUTE), problem=stairs)
    practised_earlier = attempt(2, D1, main=BRUTE)

    owed = corrections.owed([practised_later, practised_earlier])

    assert [(c.problem["number"], c.due) for c in owed] == [(121, D1 + INTERVAL), (70, D2 + INTERVAL)]
    assert corrections.owed([]) == []


def test_outstanding_lists_the_soonest_due_first_then_by_number(tmp_path):
    conn = make_db(tmp_path)
    for number in (53, 70, 121):
        enrich.save_intended(conn, number, "dp-1d")
    solve(conn, 53, D2, main=BRUTE)
    solve(conn, 121, D1, main=BRUTE)
    solve(conn, 70, D1, main=BRUTE)

    assert [c.problem["number"] for c in corrections.outstanding(conn)] == [70, 121, 53]
