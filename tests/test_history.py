"""The one read of practice history, against the real joins.

Every reader of this history - mastery, approach practice, the SM-2 replay, the plan's
"why is this back" note - is pure over what load() returns, so a wrong join here is the
one place it can go wrong for all of them at once. These tests pin the three things the
readers rely on: the order, what a left join must not drop, and which review lands on
which attempt.
"""

import json
from datetime import date

import pytest
from conftest import TWO_SUM, seed_db, tag_solution

from coach import enrich, history

D1 = date(2026, 9, 12)
D2 = date(2026, 9, 15)

PROBLEMS = [
    *TWO_SUM,
    {
        "number": 121,
        "slug": "best-time-to-buy-and-sell-stock",
        "title": "Best Time to Buy and Sell Stock",
        "difficulty": "Easy",
        "official_tags": '["array"]',
        "paid_only": 0,
    },
]


def issues(*categories):
    return [{"category": c, "description": "..."} for c in categories]


@pytest.fixture
def conn(tmp_path, monkeypatch):
    connection = seed_db(tmp_path, monkeypatch, PROBLEMS)
    yield connection
    connection.close()


def solve(conn, number, day, outcome="clean", minutes=None, main=None, secondary=(), review=None):
    """One attempt, its solution, and optionally its tags and its review.

    `main=None` leaves the solve untagged, which is what a solve logged while the API
    was unavailable looks like until `coach enrich` backfills it.
    """
    attempt_id = conn.execute(
        "INSERT INTO attempts (problem_number, date, outcome, minutes) VALUES (?, ?, ?, ?)",
        (number, day.isoformat(), outcome, minutes),
    ).lastrowid
    solution_id = conn.execute(
        "INSERT INTO solutions (problem_number, attempt_id, code, created_at) VALUES (?, ?, 'c', ?)",
        (number, attempt_id, day.isoformat()),
    ).lastrowid
    if main is not None:
        tag_solution(conn, solution_id, *main, secondary=secondary)
    if review is not None:
        verdict, found = review
        conn.execute(
            "INSERT INTO reviews (solution_id, verdict, issues, created_at) VALUES (?, ?, ?, ?)",
            (solution_id, verdict, json.dumps(issues(*found)), day.isoformat()),
        )
    return attempt_id


def test_loads_every_attempt_oldest_first_across_problems(conn):
    """Chronological, not grouped by problem: mastery folds one pattern's attempts in
    this order, so ordering by problem first would score a pattern out of sequence."""
    second = solve(conn, 121, D2)
    first = solve(conn, 1, D1)

    assert [a.id for a in history.load(conn)] == [first, second]


def test_two_attempts_on_one_day_keep_logging_order(conn):
    """A day's attempts tie on the date, so the id breaks the tie - the order they happened."""
    first = solve(conn, 1, D1, outcome="failed")
    second = solve(conn, 1, D1, outcome="clean")

    assert [a.id for a in history.load(conn)] == [first, second]


def test_an_untagged_solve_is_loaded_with_unknown_patterns(conn):
    """Never dropped and never an empty list: the solve happened, and what it used is
    unknown - which approach practice must not read as evidence of anything."""
    solve(conn, 1, D1)

    [attempt] = history.load(conn)
    assert attempt.tagged is False
    assert attempt.main_patterns is None
    assert attempt.secondary_patterns == ()


def test_a_tagged_solve_carries_both_pattern_lists(conn):
    solve(conn, 1, D1, main=["dfs", "dp-knapsack"], secondary=["hashmap"])

    [attempt] = history.load(conn)
    assert attempt.tagged is True
    assert attempt.main_patterns == ("dfs", "dp-knapsack")
    assert attempt.secondary_patterns == ("hashmap",)


def test_an_attempt_with_no_solution_still_loads(conn):
    """The solve is left-joined, so an attempt logged without stored code is still
    practice that happened - and still a day the SM-2 replay has to grade."""
    conn.execute(
        "INSERT INTO attempts (problem_number, date, outcome) VALUES (1, ?, 'failed')",
        (D1.isoformat(),),
    )

    [attempt] = history.load(conn)
    assert attempt.outcome == "failed"
    assert attempt.tagged is False


def test_a_review_lands_only_on_the_attempt_it_judges(conn):
    """A review is keyed by solution, so a second solve of the same problem is ungraded
    by it - the bug that would re-lapse a problem its retry had already fixed."""
    reviewed = solve(conn, 1, D1, review=("needs-work", ("bug",)))
    retried = solve(conn, 1, D2)

    graded = {a.id: a for a in history.load(conn)}
    assert graded[reviewed].verdict == "needs-work"
    assert graded[reviewed].finding == "bug"
    assert graded[retried].verdict is None
    assert graded[retried].finding is None


@pytest.mark.parametrize(
    "outcome, review, expected",
    [
        ("clean", None, 5),
        ("hints", None, 2),
        # a review only ever caps: a bug holds a clean solve at 1, an "optimal" lifts nothing
        ("clean", ("needs-work", ("bug",)), 1),
        ("clean", ("needs-work", ("edge-case",)), 2),
        ("hints", ("optimal", ()), 2),
        # a complexity finding describes correct code, so it caps nothing
        ("clean", ("acceptable", ("complexity",)), 5),
    ],
)
def test_grade_is_the_outcome_capped_by_the_review(conn, outcome, review, expected):
    solve(conn, 1, D1, outcome=outcome, review=review)

    [attempt] = history.load(conn)
    assert attempt.grade == expected


def test_number_narrows_to_one_problem(conn):
    solve(conn, 1, D1)
    wanted = solve(conn, 121, D2)

    assert [a.id for a in history.load(conn, 121)] == [wanted]


def test_each_attempt_carries_its_problem_and_canonical_set(conn):
    solve(conn, 121, D1)
    enrich.save_intended(conn, 121, "dp-1d", ["greedy"])

    [attempt] = history.load(conn, 121)
    assert attempt.problem.number == 121
    assert attempt.problem.slug == "best-time-to-buy-and-sell-stock"
    assert attempt.problem.title == "Best Time to Buy and Sell Stock"
    assert attempt.problem.difficulty == "Easy"
    assert attempt.problem.canonical == enrich.Canonical("dp-1d", ["greedy"])


def test_a_problem_never_enriched_has_an_empty_canonical_set(conn):
    """Unknown, not wrong: approach practice leaves a problem alone until one is stored."""
    solve(conn, 1, D1)

    [attempt] = history.load(conn)
    assert attempt.problem.canonical == enrich.Canonical(None, [])


def test_minutes_travel_with_the_attempt(conn):
    """The weekly table shows them, and nothing else carries them."""
    solve(conn, 1, D1, minutes=25)

    [attempt] = history.load(conn)
    assert attempt.minutes == 25


def test_by_problem_groups_without_disturbing_the_order(conn):
    one_first = solve(conn, 1, D1)
    other = solve(conn, 121, D1)
    one_second = solve(conn, 1, D2)

    grouped = history.by_problem(history.load(conn))
    assert [a.id for a in grouped[1]] == [one_first, one_second]
    assert [a.id for a in grouped[121]] == [other]


def test_by_problem_of_an_empty_history_is_empty(conn):
    assert history.by_problem(history.load(conn)) == {}
