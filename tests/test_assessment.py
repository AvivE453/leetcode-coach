import json
from datetime import date

import pytest

from coach import assessment, db, enrich, history


def issues(*categories):
    return [{"category": c, "description": "..."} for c in categories]


@pytest.mark.parametrize(
    "verdict, found, expected",
    [
        (None, (), None),
        ("optimal", (), None),
        ("acceptable", ("complexity",), None),
        # needs-work is adverse even when it names no failing input
        ("needs-work", (), "unspecified"),
        ("needs-work", ("complexity",), "unspecified"),
        # the categories outrank a verdict that contradicts them
        ("optimal", ("bug",), "bug"),
        ("acceptable", ("edge-case",), "edge-case"),
        # and the worst category wins, whatever order they came in
        ("needs-work", ("edge-case", "bug"), "bug"),
        ("needs-work", ("complexity", "edge-case"), "edge-case"),
    ],
)
def test_correctness_finding(verdict, found, expected):
    assert assessment.correctness_finding(verdict, issues(*found)) == expected


REVIEWS = {
    "no review": (None, ()),
    "optimal": ("optimal", ()),
    "complexity only": ("acceptable", ("complexity",)),
    "bug": ("needs-work", ("bug",)),
    "edge-case": ("needs-work", ("edge-case",)),
    "unspecified": ("needs-work", ()),
}

# outcome -> its grade under each review above, in the same order
EXPECTED_QUALITY = {
    "clean": (5, 5, 5, 1, 2, 2),
    "struggled": (3, 3, 3, 1, 2, 2),
    "hints": (2, 2, 2, 1, 2, 2),
    "failed": (1, 1, 1, 1, 1, 1),
}


@pytest.mark.parametrize(
    "outcome, review, expected",
    [
        (outcome, review, grade)
        for outcome, grades in EXPECTED_QUALITY.items()
        for review, grade in zip(REVIEWS, grades, strict=True)
    ],
)
def test_effective_quality_caps_the_outcome_and_never_raises_it(outcome, review, expected):
    verdict, found = REVIEWS[review]
    assert assessment.effective_quality(outcome, verdict, issues(*found)) == expected


def make_db(tmp_path):
    conn = db.connect(tmp_path / "test.db")
    db.init_schema(conn)
    conn.executemany(
        "INSERT INTO problems (number, slug, title, difficulty) VALUES (?, ?, ?, 'Easy')",
        [(1, "two-sum", "Two Sum"), (15, "3sum", "3Sum")],
    )
    return conn


def add_solve(conn, day, review=None, problem=1):
    """One clean attempt and its solution, reviewed as (verdict, categories) when given."""
    attempt_id = conn.execute(
        "INSERT INTO attempts (problem_number, date, outcome) VALUES (?, ?, 'clean')",
        (problem, day),
    ).lastrowid
    solution_id = conn.execute(
        "INSERT INTO solutions (problem_number, attempt_id, code, created_at) VALUES (?, ?, 'c', ?)",
        (problem, attempt_id, day),
    ).lastrowid
    if review:
        verdict, found = review
        conn.execute(
            "INSERT INTO reviews (solution_id, verdict, issues, created_at) VALUES (?, ?, ?, ?)",
            (solution_id, verdict, json.dumps(issues(*found)), day),
        )


BUG = ("needs-work", ("bug",))
EDGE = ("needs-work", ("edge-case",))


def test_findings_reads_the_database_only_the_last_practice_day(tmp_path):
    """A later solve moves past an old finding, even unreviewed: it is trusted as logged."""
    conn = make_db(tmp_path)
    add_solve(conn, "2026-09-01", BUG)
    add_solve(conn, "2026-09-08")
    add_solve(conn, "2026-09-01", EDGE, problem=15)

    assert assessment.findings(history.load(conn)) == {15: "edge-case"}


def test_a_same_day_retry_does_not_clear_a_finding(tmp_path):
    """The schedule grades the day by its worst attempt, so the reason must too."""
    conn = make_db(tmp_path)
    add_solve(conn, "2026-09-01", BUG)
    add_solve(conn, "2026-09-01")

    assert assessment.findings(history.load(conn)) == {1: "bug"}


@pytest.mark.parametrize(
    "day_reviews, expected",
    [
        ([EDGE, BUG], "bug"),
        ([BUG, EDGE], "bug"),
        ([("needs-work", ()), EDGE], "edge-case"),
        ([EDGE, ("needs-work", ())], "edge-case"),
    ],
)
def test_the_worst_finding_on_the_day_wins(tmp_path, day_reviews, expected):
    conn = make_db(tmp_path)
    for review in day_reviews:
        add_solve(conn, "2026-09-01", review)

    assert assessment.findings(history.load(conn)) == {1: expected}


def test_problems_without_a_finding_are_left_out(tmp_path):
    conn = make_db(tmp_path)
    add_solve(conn, "2026-09-01", ("optimal", ()))
    add_solve(conn, "2026-09-01", ("acceptable", ("complexity",)), problem=15)

    assert assessment.findings(history.load(conn)) == {}


def attempt(number, day, review=None):
    """One loaded attempt, as history.load() would have returned it."""
    verdict, found = review or (None, ())
    return history.Attempt(
        id=0,
        problem=history.Problem(
            number=number,
            slug=f"p{number}",
            title=f"Problem {number}",
            difficulty="Easy",
            canonical=enrich.Canonical(None, []),
        ),
        day=date.fromisoformat(day),
        outcome="clean",
        minutes=None,
        main_patterns=None,
        secondary_patterns=(),
        verdict=verdict,
        issues=tuple(issues(*found)),
    )


def test_findings_is_pure_over_a_loaded_history():
    """No connection: the join is history.load()'s, and this only reads what it returned."""
    assert assessment.findings(
        [
            attempt(1, "2026-09-01", BUG),
            attempt(1, "2026-09-01"),  # a same-day retry does not clear it
            attempt(15, "2026-09-01", EDGE),
            attempt(15, "2026-09-08"),  # a later day moves past it
        ]
    ) == {1: "bug"}


def test_findings_reads_the_last_day_from_the_attempts_not_their_order():
    """history.load() is oldest first, but the rule is about days, so nothing may turn on
    where an attempt sits in the list."""
    newest_first = [attempt(1, "2026-09-08"), attempt(1, "2026-09-01", BUG)]

    assert assessment.findings(newest_first) == {}


def test_findings_of_an_empty_history_is_empty():
    assert assessment.findings([]) == {}
