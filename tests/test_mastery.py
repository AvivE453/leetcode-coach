import json

import pytest

from coach import db, mastery


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


def add_solve(conn, day, outcome, pattern, review=None):
    attempt_id = conn.execute(
        "INSERT INTO attempts (problem_number, date, outcome) VALUES (1, ?, ?)",
        (day, outcome),
    ).lastrowid
    solution_id = conn.execute(
        "INSERT INTO solutions (problem_number, attempt_id, code, created_at) VALUES (1, ?, 'c', ?)",
        (attempt_id, day),
    ).lastrowid
    conn.execute(
        """
        INSERT INTO enrichments (solution_id, pattern, secondary_patterns, data_structures)
        VALUES (?, ?, '[]', '[]')
        """,
        (solution_id, pattern),
    )
    if review:
        verdict, found = review
        conn.execute(
            """
            INSERT INTO reviews (solution_id, verdict, strengths, issues, time_complexity,
                                 space_complexity, optimal_time_complexity, created_at)
            VALUES (?, ?, '[]', ?, 'O(n)', 'O(1)', 'O(n)', ?)
            """,
            (solution_id, verdict, json.dumps(issues(*found)), day),
        )
    return solution_id


def test_recompute_scores_each_pattern_in_date_order(tmp_path):
    conn = make_db(tmp_path)
    add_solve(conn, "2026-08-01", "clean", "hashmap")
    add_solve(conn, "2026-08-02", "failed", "hashmap")
    add_solve(conn, "2026-08-03", "struggled", "dp-1d")

    mastery.recompute_all(conn)

    assert mastery.scores(conn) == pytest.approx({"hashmap": 4.2, "dp-1d": 3.0})
    row = conn.execute("SELECT * FROM pattern_scores WHERE pattern = 'hashmap'").fetchone()
    assert row["attempts"] == 2


def test_recompute_is_a_pure_replay_of_history(tmp_path):
    """Running it twice changes nothing - the table is a cache, not an accumulator."""
    conn = make_db(tmp_path)
    add_solve(conn, "2026-08-01", "clean", "hashmap")
    add_solve(conn, "2026-08-02", "struggled", "hashmap")

    mastery.recompute_all(conn)
    once = mastery.scores(conn)
    mastery.recompute_all(conn)
    mastery.recompute_all(conn)

    assert mastery.scores(conn) == once


def test_a_late_review_rescores_the_solve_it_belongs_to(tmp_path):
    """The reason scores are replayed: reviews are on-demand and arrive later."""
    conn = make_db(tmp_path)
    add_solve(conn, "2026-08-01", "clean", "hashmap")
    solution_id = add_solve(conn, "2026-08-02", "clean", "hashmap")
    mastery.recompute_all(conn)
    assert mastery.scores(conn)["hashmap"] == 5.0

    conn.execute(
        """
        INSERT INTO reviews (solution_id, verdict, strengths, issues, time_complexity,
                             space_complexity, optimal_time_complexity, created_at)
        VALUES (?, 'needs-work', '[]', ?, 'O(n^2)', 'O(1)', 'O(n)', '2026-08-09')
        """,
        (solution_id, json.dumps(issues("bug"))),
    )
    mastery.recompute_all(conn)

    # the second solve is now 3.8, folded onto the 5.0 seed
    assert mastery.scores(conn)["hashmap"] == pytest.approx(4.76)


def test_recompute_ignores_solves_that_were_never_tagged(tmp_path):
    """No pattern means nothing to attribute the solve to."""
    conn = make_db(tmp_path)
    attempt_id = conn.execute(
        "INSERT INTO attempts (problem_number, date, outcome) VALUES (1, '2026-08-01', 'failed')"
    ).lastrowid
    conn.execute(
        "INSERT INTO solutions (problem_number, attempt_id, code, created_at) VALUES (1, ?, 'c', '2026-08-01')",
        (attempt_id,),
    )

    mastery.recompute_all(conn)

    assert mastery.scores(conn) == {}


def test_recompute_drops_scores_for_patterns_that_are_gone(tmp_path):
    conn = make_db(tmp_path)
    add_solve(conn, "2026-08-01", "clean", "hashmap")
    mastery.recompute_all(conn)

    conn.execute("DELETE FROM enrichments")
    mastery.recompute_all(conn)

    assert mastery.scores(conn) == {}
