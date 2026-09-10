import json
from datetime import date

import pytest

from coach import db, mastery, service
from coach.weekly import analyze as weekly_analyze


def issues(*categories):
    return [{"category": c, "description": "..."} for c in categories]


@pytest.mark.parametrize(
    "verdict,found,expected",
    [
        ("optimal", (), 5),
        ("acceptable", (), 4),
        ("acceptable", ("complexity",), 4),
        # two findings cap at 3, three cap at 2, five bottom out at 1
        ("acceptable", ("complexity", "edge-case"), 3),
        ("acceptable", ("complexity", "edge-case", "edge-case"), 2),
        ("optimal", ("edge-case",) * 5, 1),
        # a bug is a misunderstanding of the pattern, so it scores lowest outright
        ("needs-work", ("bug",), 1),
        ("needs-work", ("edge-case",), 2),
        ("needs-work", ("edge-case", "complexity"), 2),
        ("needs-work", ("bug", "edge-case", "complexity"), 1),
    ],
)
def test_review_mastery_scores_verdict_against_issue_count(verdict, found, expected):
    assert mastery.review_mastery(verdict, issues(*found)) == expected


def test_attempt_score_falls_back_to_the_outcome_without_a_review():
    """Most solves are never reviewed - the outcome then carries full weight."""
    assert mastery.attempt_score("clean") == 5.0
    assert mastery.attempt_score("struggled") == 3.0
    assert mastery.attempt_score("hints") == 2.0
    assert mastery.attempt_score("failed") == 1.0


def test_attempt_score_blends_the_review_at_three_tenths():
    # felt clean, carried a bug: 0.7*5 + 0.3*1
    assert mastery.attempt_score("clean", "needs-work", issues("bug")) == pytest.approx(3.8)
    # felt rough, came out optimal: 0.7*3 + 0.3*5
    assert mastery.attempt_score("struggled", "optimal") == pytest.approx(3.6)
    assert mastery.attempt_score("clean", "optimal") == pytest.approx(5.0)


def test_fold_seeds_on_the_first_attempt_and_eases_toward_later_ones():
    assert mastery.fold([]) is None
    assert mastery.fold([5.0]) == 5.0
    # one bad solve moves a perfect record by alpha, not all the way down
    assert mastery.fold([5.0, 1.0]) == pytest.approx(4.2)
    assert mastery.fold([5.0, 1.0, 1.0]) == pytest.approx(3.56)
    # and a steady run converges on what it keeps seeing
    assert mastery.fold([3.0] * 8) == pytest.approx(3.0)


def make_db(tmp_path):
    conn = db.connect(tmp_path / "test.db")
    db.init_schema(conn)
    conn.execute(
        "INSERT INTO problems (number, slug, title, difficulty) VALUES (1, 'two-sum', 'Two Sum', 'Easy')"
    )
    return conn


def add_solve(conn, day, outcome, pattern, review=None, secondary=()):
    """One attempt and its solution; tagged when `pattern` is given, reviewed when `review` is."""
    attempt_id = conn.execute(
        "INSERT INTO attempts (problem_number, date, outcome) VALUES (1, ?, ?)",
        (day, outcome),
    ).lastrowid
    solution_id = conn.execute(
        "INSERT INTO solutions (problem_number, attempt_id, code, created_at) VALUES (1, ?, 'c', ?)",
        (attempt_id, day),
    ).lastrowid
    if pattern:
        conn.execute(
            """
            INSERT INTO enrichments (solution_id, pattern, secondary_patterns, data_structures)
            VALUES (?, ?, ?, '[]')
            """,
            (solution_id, pattern, json.dumps(list(secondary))),
        )
    if review:
        add_review(conn, solution_id, *review, day=day)
    return solution_id


def add_review(conn, solution_id, verdict, found=(), day="2026-08-01"):
    conn.execute(
        """
        INSERT INTO reviews (solution_id, verdict, strengths, issues, time_complexity,
                             space_complexity, optimal_time_complexity, created_at)
        VALUES (?, ?, '[]', ?, 'O(n)', 'O(1)', 'O(n)', ?)
        """,
        (solution_id, verdict, json.dumps(issues(*found)), day),
    )


PIN_TODAY = date(2026, 9, 7)  # so the weekly window is 2026-09-01 .. 2026-09-07


def add_pinned_history(conn):
    """One history exercising every rule the mastery number follows."""
    # hashmap - on-track. Inserted out of date order; two solves tie on 09-05, so the
    # id breaks the tie; and the 08-25 solve is only reviewed after the window opened.
    late = add_solve(conn, "2026-08-25", "clean", "hashmap")
    add_solve(
        conn, "2026-08-10", "struggled", "hashmap", review=("acceptable", ("complexity", "edge-case"))
    )
    add_solve(conn, "2026-09-05", "clean", "hashmap")
    add_solve(conn, "2026-09-05", "failed", "hashmap")
    add_solve(conn, "2026-08-30", "hints", "hashmap", secondary=["two-pointers"])
    add_review(conn, late, "needs-work", ("bug",), day="2026-09-06")
    # dp-1d - weak: exactly five attempts, mastery under 2.5, every review rule in play
    add_solve(conn, "2026-08-20", "failed", "dp-1d")
    add_solve(conn, "2026-08-21", "struggled", "dp-1d", review=("needs-work", ("edge-case",)))
    add_solve(
        conn, "2026-08-22", "hints", "dp-1d",
        review=("acceptable", ("complexity", "edge-case", "edge-case")),
    )
    add_solve(conn, "2026-09-02", "failed", "dp-1d", review=("needs-work", ("bug",)))
    add_solve(conn, "2026-09-03", "clean", "dp-1d", review=("optimal", ("edge-case",) * 5))
    # graph - four attempts: too early to judge, however low it scores
    add_solve(conn, "2026-09-01", "failed", "graph", review=("acceptable", ()))
    for day in ("2026-09-02", "2026-09-03", "2026-09-04"):
        add_solve(conn, day, "failed", "graph")
    # never tagged: a solve in the week, with nothing to score it under
    add_solve(conn, "2026-09-06", "clean", None)
    conn.commit()


def test_scoring_behavior_is_pinned(tmp_path):
    """Every reader of mastery, over one history, against numbers worked by hand.

    Per solve: 0.7 x outcome + 0.3 x review, the review capped by its issue count.
    dp-1d: 1, 2.7, 2.0, 1.0, 3.8. hashmap in date order: 3.0, 3.8 (its late bug
    review), 2, 5, 1. graph: 1.9, 1, 1, 1. Each folded oldest-first at alpha 0.2.
    """
    conn = make_db(tmp_path)
    add_pinned_history(conn)

    analysis = weekly_analyze.analyze(conn, PIN_TODAY)
    assert analysis["patterns"] == [
        {"pattern": "dp-1d", "attempts": 5, "rough": 4, "struggle_rate": 0.8,
         "score": pytest.approx(1.86208), "last_date": date(2026, 9, 3)},
        {"pattern": "graph", "attempts": 4, "rough": 4, "struggle_rate": 1.0,
         "score": pytest.approx(1.4608), "last_date": date(2026, 9, 4)},
        {"pattern": "hashmap", "attempts": 5, "rough": 3, "struggle_rate": 0.6,
         "score": pytest.approx(2.87392), "last_date": date(2026, 9, 5)},
    ]
    assert analysis["weak_patterns"] == ["dp-1d"]

    assert service.pattern_table(conn) == [
        {"pattern": "dp-1d", "solved": 1, "score": pytest.approx(1.86208), "attempts": 5, "rough": 4},
        {"pattern": "graph", "solved": 1, "score": pytest.approx(1.4608), "attempts": 4, "rough": 4},
        {"pattern": "hashmap", "solved": 1, "score": pytest.approx(2.87392), "attempts": 5, "rough": 3},
        # only ever a secondary: it has coverage, but no practice to score
        {"pattern": "two-pointers", "solved": 1, "score": None, "attempts": None, "rough": None},
    ]

    review = service.weekly_review(conn, PIN_TODAY)
    assert len(review.attempts) == 9  # the untagged solve included
    assert [
        (p.pattern, p.attempts_week, p.attempts_total, p.score, p.score_before, p.standing)
        for p in review.patterns
    ] == [
        ("dp-1d", 2, 5, pytest.approx(1.86208), pytest.approx(1.472), "weak"),
        # the late review re-scores its pre-window solve on both sides of the cut
        ("hashmap", 2, 5, pytest.approx(2.87392), pytest.approx(2.928), "on-track"),
        ("graph", 4, 4, pytest.approx(1.4608), None, "too-early"),
    ]


def test_is_weak_needs_both_a_low_score_and_enough_attempts():
    assert mastery.is_weak(2.49, mastery.WEAK_MIN_ATTEMPTS) is True
    assert mastery.is_weak(mastery.WEAK_SCORE, mastery.WEAK_MIN_ATTEMPTS) is False
    assert mastery.is_weak(1.0, mastery.WEAK_MIN_ATTEMPTS - 1) is False


def test_load_history_scores_each_solve_oldest_first(tmp_path):
    """Date first, then logging order - so a same-day pair folds as it was logged."""
    conn = make_db(tmp_path)
    add_solve(conn, "2026-08-02", "failed", "hashmap")
    add_solve(
        conn, "2026-08-01", "clean", "hashmap", review=("acceptable", ("complexity", "edge-case"))
    )
    add_solve(conn, "2026-08-01", "struggled", "dp-1d")

    assert [(a.pattern, a.day, a.outcome, a.score) for a in mastery.load_history(conn)] == [
        ("hashmap", date(2026, 8, 1), "clean", pytest.approx(4.4)),  # 0.7*5 + 0.3*3
        ("dp-1d", date(2026, 8, 1), "struggled", 3.0),
        ("hashmap", date(2026, 8, 2), "failed", 1.0),
    ]


def test_load_history_leaves_out_solves_that_were_never_tagged(tmp_path):
    """No pattern means nothing to attribute the solve to."""
    conn = make_db(tmp_path)
    add_solve(conn, "2026-08-01", "failed", None)

    assert mastery.load_history(conn) == []


def test_pattern_stats_takes_every_field_from_the_same_attempts(tmp_path):
    conn = make_db(tmp_path)
    add_solve(conn, "2026-08-01", "clean", "hashmap")
    add_solve(conn, "2026-08-02", "failed", "hashmap")
    add_solve(conn, "2026-08-03", "struggled", "dp-1d")

    assert mastery.pattern_stats(mastery.load_history(conn)) == [
        {"pattern": "dp-1d", "attempts": 1, "rough": 1, "struggle_rate": 1.0,
         "score": 3.0, "last_date": date(2026, 8, 3)},
        {"pattern": "hashmap", "attempts": 2, "rough": 1, "struggle_rate": 0.5,
         "score": pytest.approx(4.2), "last_date": date(2026, 8, 2)},
    ]
    assert mastery.pattern_stats([]) == []


def test_a_late_review_counts_the_moment_it_is_saved(tmp_path):
    """Reviews are on-demand and arrive days later; nothing has to run after saving one."""
    conn = make_db(tmp_path)
    add_solve(conn, "2026-08-01", "clean", "hashmap")
    solution_id = add_solve(conn, "2026-08-02", "clean", "hashmap")
    assert mastery.pattern_stats(mastery.load_history(conn))[0]["score"] == 5.0

    add_review(conn, solution_id, "needs-work", ("bug",), day="2026-08-09")

    # the second solve is now 3.8, folded onto the 5.0 seed
    assert mastery.pattern_stats(mastery.load_history(conn))[0]["score"] == pytest.approx(4.76)
