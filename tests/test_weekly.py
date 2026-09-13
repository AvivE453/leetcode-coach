import json
from datetime import date, timedelta

import pytest
from conftest import tag_solution

from coach import corrections, db
from coach.weekly import analyze as weekly_analyze
from coach.weekly import collect as weekly_collect
from coach.weekly import plan as weekly_plan

TODAY = date(2026, 8, 31)
# A solve this long ago that used the wrong approach owes approach practice today.
PRACTICE_DUE_TODAY = TODAY - timedelta(days=corrections.CORRECTION_INTERVAL_DAYS)


def make_db(tmp_path):
    conn = db.connect(tmp_path / "test.db")
    db.init_schema(conn)
    return conn


def add_problem(conn, number, slug, title, difficulty="Easy", tags=(), blind75=True, intended=None):
    conn.execute(
        """
        INSERT INTO problems (number, slug, title, difficulty, official_tags, paid_only,
                              in_blind75, intended_pattern)
        VALUES (?, ?, ?, ?, ?, 0, ?, ?)
        """,
        (number, slug, title, difficulty, json.dumps(list(tags)), int(blind75), intended),
    )


def add_attempt(conn, number, day, outcome="clean", pattern=None, minutes=None):
    attempt_id = conn.execute(
        "INSERT INTO attempts (problem_number, date, outcome, minutes) VALUES (?, ?, ?, ?)",
        (number, day.isoformat(), outcome, minutes),
    ).lastrowid
    solution_id = conn.execute(
        "INSERT INTO solutions (problem_number, attempt_id, code, created_at) VALUES (?, ?, 'c', ?)",
        (number, attempt_id, day.isoformat()),
    ).lastrowid
    if pattern:
        tag_solution(conn, solution_id, pattern)
    return solution_id


def set_due(conn, number, day):
    conn.execute(
        """
        INSERT INTO review_state (problem_number, ease, interval_days, next_due, reps, lapses)
        VALUES (?, 2.5, 1.0, ?, 1, 0)
        """,
        (number, day.isoformat()),
    )


def reasons(item):
    """An item's reasons as (kind, text) pairs, in the order the plan gave them."""
    return [(r.kind, r.text) for r in item.reasons]


def test_collect_window_excludes_older_attempts(tmp_path):
    conn = make_db(tmp_path)
    add_problem(conn, 1, "two-sum", "Two Sum")
    add_attempt(conn, 1, TODAY - timedelta(days=2), pattern="hashmap")
    add_attempt(conn, 1, TODAY - timedelta(days=20))

    week = weekly_collect.collect(conn, TODAY)
    assert len(week["attempts"]) == 1
    assert week["distinct_problems"] == 1
    assert week["attempts"][0]["main_patterns"] == ["hashmap"]
    assert week["start"] == TODAY - timedelta(days=6)


def test_collect_empty_week(tmp_path):
    conn = make_db(tmp_path)
    week = weekly_collect.collect(conn, TODAY)
    assert week["attempts"] == []
    assert week["distinct_problems"] == 0


def test_analyze_flags_weak_and_stale_patterns(tmp_path):
    conn = make_db(tmp_path)
    add_problem(conn, 1, "two-sum", "Two Sum")
    add_problem(conn, 2, "coin-change", "Coin Change")
    add_problem(conn, 3, "lru-cache", "LRU Cache")
    add_problem(conn, 4, "3sum", "3Sum")
    # weak: five failures, so mastery bottoms out at 1.0
    for _ in range(5):
        add_attempt(conn, 2, TODAY - timedelta(days=1), outcome="failed", pattern="dp-1d")
    # NOT weak: the same 100% struggle rate, but solved every time - mastery 3.0
    for _ in range(5):
        add_attempt(conn, 4, TODAY - timedelta(days=1), outcome="struggled", pattern="two-pointers")
    # strong: single clean attempt
    add_attempt(conn, 1, TODAY - timedelta(days=1), outcome="clean", pattern="hashmap")
    # stale: clean but 60 days ago
    add_attempt(conn, 3, TODAY - timedelta(days=60), outcome="clean", pattern="design")

    analysis = weekly_analyze.analyze(conn, TODAY)
    assert analysis["weak_patterns"] == ["dp-1d"]
    assert analysis["stale_patterns"] == ["design"]
    rates = {p["pattern"]: p["struggle_rate"] for p in analysis["patterns"]}
    assert rates["dp-1d"] == 1.0
    assert rates["two-pointers"] == 1.0
    assert rates["hashmap"] == 0.0
    scores = {p["pattern"]: p["score"] for p in analysis["patterns"]}
    assert scores == pytest.approx({"dp-1d": 1.0, "two-pointers": 3.0, "hashmap": 5.0, "design": 5.0})


def test_analyze_needs_five_attempts_before_calling_a_pattern_weak(tmp_path):
    conn = make_db(tmp_path)
    add_problem(conn, 1, "coin-change", "Coin Change")
    for _ in range(4):
        add_attempt(conn, 1, TODAY - timedelta(days=1), outcome="failed", pattern="dp-1d")

    analysis = weekly_analyze.analyze(conn, TODAY)
    assert analysis["weak_patterns"] == []

    add_attempt(conn, 1, TODAY, outcome="failed", pattern="dp-1d")
    assert weekly_analyze.analyze(conn, TODAY)["weak_patterns"] == ["dp-1d"]


def test_analyze_reports_due_and_curriculum(tmp_path):
    conn = make_db(tmp_path)
    add_problem(conn, 1, "two-sum", "Two Sum")
    add_problem(conn, 2, "coin-change", "Coin Change")
    add_attempt(conn, 1, TODAY - timedelta(days=1), pattern="hashmap")
    set_due(conn, 1, TODAY - timedelta(days=1))
    set_due(conn, 2, TODAY + timedelta(days=30))  # outside the 7-day horizon

    analysis = weekly_analyze.analyze(conn, TODAY)
    assert [r["number"] for r in analysis["due"]] == [1]
    assert analysis["curriculum"]["blind75"] == {"done": 1, "total": 2}


def test_analyze_lookahead_narrows_due_to_today(tmp_path):
    """The daily plan passes lookahead_days=0 so it only sees what is owed today.

    Solving a review early re-anchors SM-2 from today and shortens the interval,
    so a four-slot list must not be padded with Friday's reviews.
    """
    conn = make_db(tmp_path)
    add_problem(conn, 1, "two-sum", "Two Sum")
    add_problem(conn, 2, "coin-change", "Coin Change")
    set_due(conn, 1, TODAY)
    set_due(conn, 2, TODAY + timedelta(days=3))

    assert [r["number"] for r in weekly_analyze.analyze(conn, TODAY)["due"]] == [1, 2]
    assert [
        r["number"] for r in weekly_analyze.analyze(conn, TODAY, lookahead_days=0)["due"]
    ] == [1]


def test_analyze_splits_approach_practice_at_the_lookahead_horizon(tmp_path):
    conn = make_db(tmp_path)
    add_problem(conn, 2, "maximum-subarray", "Maximum Subarray", intended="dp-1d")
    add_problem(conn, 3, "house-robber", "House Robber", intended="dp-1d")
    add_attempt(conn, 2, PRACTICE_DUE_TODAY, pattern="prefix-sum")
    add_attempt(conn, 3, TODAY, pattern="prefix-sum")  # due three days from now

    def split(lookahead_days):
        analysis = weekly_analyze.analyze(conn, TODAY, lookahead_days=lookahead_days)
        return (
            [c.problem["number"] for c in analysis["corrections_due"]],
            [c.problem["number"] for c in analysis["corrections_upcoming"]],
        )

    assert split(0) == ([2], [3])
    assert split(weekly_analyze.PLAN_LOOKAHEAD_DAYS) == ([2, 3], [])


def test_plan_orders_reviews_then_approach_practice_then_weak(tmp_path):
    conn = make_db(tmp_path)
    add_problem(conn, 1, "two-sum", "Two Sum", tags=["hash-table"])
    add_problem(conn, 2, "maximum-subarray", "Maximum Subarray", tags=["dynamic-programming"],
                intended="dp-1d")
    add_problem(conn, 3, "coin-change", "Coin Change", tags=["dynamic-programming"])
    add_problem(conn, 4, "house-robber", "House Robber", tags=["dynamic-programming"])
    add_attempt(conn, 1, TODAY - timedelta(days=1), pattern="hashmap")
    add_attempt(conn, 2, PRACTICE_DUE_TODAY, outcome="struggled", pattern="prefix-sum")
    set_due(conn, 1, TODAY)

    analysis = weekly_analyze.analyze(conn, TODAY)
    analysis["weak_patterns"] = ["dp-1d"]
    items = weekly_plan.build_plan(conn, analysis, target=10)

    assert (items[0].number, reasons(items[0])) == (1, [("review", f"review due {TODAY.isoformat()}")])
    assert (items[1].number, reasons(items[1])) == (
        2,
        [("re-solve", "practice an accepted approach: dp-1d")],
    )
    weak = [i for i in items if reasons(i) == [("weak-pattern", "weak pattern: dp-1d")]]
    assert {i.number for i in weak} == {3, 4}


def test_plan_labels_every_reason_with_the_rule_that_gave_it(tmp_path):
    """`kind` is what the web UI styles, and it is set where the rule fires.

    All four rules in one plan: the chip a reader sees must say which one put the
    problem there, and no wording change to a reason's text can move it between them.
    """
    conn = make_db(tmp_path)
    add_problem(conn, 1, "two-sum", "Two Sum", tags=["hash-table"])
    add_problem(conn, 2, "maximum-subarray", "Maximum Subarray", tags=["dynamic-programming"],
                intended="dp-1d")
    add_problem(conn, 3, "coin-change", "Coin Change", tags=["dynamic-programming"])
    add_problem(conn, 4, "valid-anagram", "Valid Anagram", tags=["string"])
    add_attempt(conn, 1, TODAY - timedelta(days=1), pattern="hashmap")
    add_attempt(conn, 2, PRACTICE_DUE_TODAY, outcome="struggled", pattern="prefix-sum")
    set_due(conn, 1, TODAY)

    analysis = weekly_analyze.analyze(conn, TODAY)
    analysis["weak_patterns"] = ["dp-1d"]
    kinds = {i.number: [r.kind for r in i.reasons] for i in weekly_plan.build_plan(conn, analysis, target=10)}

    # #3 carries the dynamic-programming tag, so the weak dp-1d pattern claims it;
    # #4 has no weak tag and falls through to plain curriculum progression.
    assert kinds == {1: ["review"], 2: ["re-solve"], 3: ["weak-pattern"], 4: ["curriculum"]}


def test_plan_respects_target_and_dedupes(tmp_path):
    conn = make_db(tmp_path)
    for n in range(1, 8):
        add_problem(conn, n, f"p{n}", f"Problem {n}", tags=["hash-table"])
    set_due(conn, 1, TODAY)

    analysis = weekly_analyze.analyze(conn, TODAY)
    items = weekly_plan.build_plan(conn, analysis, target=3)
    assert len(items) == 3
    assert len({i.number for i in items}) == 3


def test_plan_caps_hard_problems_for_new_picks(tmp_path):
    conn = make_db(tmp_path)
    for n in range(1, 11):
        add_problem(conn, n, f"h{n}", f"Hard {n}", difficulty="Hard")
    add_problem(conn, 20, "easy-one", "Easy One", difficulty="Easy")

    analysis = weekly_analyze.analyze(conn, TODAY)
    items = weekly_plan.build_plan(conn, analysis, target=10)
    hard = [i for i in items if i.difficulty == "Hard"]
    assert len(hard) == weekly_plan.hard_cap(10) == 2


def test_plan_keeps_due_reviews_even_when_hard(tmp_path):
    conn = make_db(tmp_path)
    for n in range(1, 6):
        add_problem(conn, n, f"h{n}", f"Hard {n}", difficulty="Hard")
        set_due(conn, n, TODAY)

    analysis = weekly_analyze.analyze(conn, TODAY)
    items = weekly_plan.build_plan(conn, analysis, target=10)
    assert len(items) == 5
    assert all(reasons(i) == [("review", f"review due {TODAY.isoformat()}")] for i in items)


def add_review(conn, solution_id, verdict, *categories):
    conn.execute(
        "INSERT INTO reviews (solution_id, verdict, issues, created_at) VALUES (?, ?, ?, ?)",
        (
            solution_id,
            verdict,
            json.dumps([{"category": c, "description": "..."} for c in categories]),
            TODAY.isoformat(),
        ),
    )


def test_plan_words_a_due_review_by_the_failure_its_review_reported(tmp_path):
    """The kind stays "review" - SM-2 brought both back - but only one says why."""
    conn = make_db(tmp_path)
    add_problem(conn, 1, "two-sum", "Two Sum")
    add_problem(conn, 2, "valid-anagram", "Valid Anagram")
    add_review(conn, add_attempt(conn, 1, TODAY - timedelta(days=3)), "needs-work", "edge-case")
    add_attempt(conn, 2, TODAY - timedelta(days=3))
    set_due(conn, 1, TODAY)
    set_due(conn, 2, TODAY)

    items = weekly_plan.build_plan(conn, weekly_analyze.analyze(conn, TODAY), target=10)

    assert {i.number: reasons(i) for i in items} == {
        1: [("review", "re-solve: review reported an edge-case failure")],
        2: [("review", f"review due {TODAY.isoformat()}")],
    }


def test_a_problem_owing_a_review_and_approach_practice_is_one_item_with_both_reasons(tmp_path):
    """The old dedupe kept the review's sentence and silently dropped the approach to use."""
    conn = make_db(tmp_path)
    add_problem(conn, 2, "maximum-subarray", "Maximum Subarray", intended="dp-1d")
    solution_id = add_attempt(conn, 2, PRACTICE_DUE_TODAY, pattern="prefix-sum")
    add_review(conn, solution_id, "needs-work", "bug")
    set_due(conn, 2, TODAY)

    analysis = weekly_analyze.analyze(conn, TODAY, lookahead_days=0)
    items = weekly_plan.build_plan(conn, analysis, target=10)

    assert [c.problem["number"] for c in analysis["corrections_due"]] == [2]  # due by both rules
    assert [(i.number, reasons(i)) for i in items] == [
        (
            2,
            [
                ("review", "re-solve: review reported a bug"),
                ("re-solve", "practice an accepted approach: dp-1d"),
            ],
        )
    ]


@pytest.mark.parametrize("days_ago, planned, upcoming", [(2, [], [2]), (3, [2], [])])
def test_approach_practice_joins_the_plan_on_its_due_date_and_not_before(
    tmp_path, days_ago, planned, upcoming
):
    """Practising a problem, however it went, must not bring it straight back: approach
    practice waits CORRECTION_INTERVAL_DAYS, and is owed from exactly that day."""
    conn = make_db(tmp_path)
    add_problem(conn, 2, "maximum-subarray", "Maximum Subarray", intended="dp-1d")
    add_attempt(conn, 2, TODAY - timedelta(days=days_ago), pattern="prefix-sum")

    analysis = weekly_analyze.analyze(conn, TODAY, lookahead_days=0)

    assert [i.number for i in weekly_plan.build_plan(conn, analysis, target=10)] == planned
    assert [c.problem["number"] for c in analysis["corrections_upcoming"]] == upcoming


def test_a_review_due_before_its_approach_practice_carries_only_its_own_reason(tmp_path, monkeypatch):
    """With today's numbers approach practice is never due after the review: both count from
    the last attempt, and SM-2's shortest step is the three-day lapse. Only a longer
    correction interval can put the review first - and then the review is listed alone,
    while the approach practice waits for its own date rather than riding along early."""
    monkeypatch.setattr(corrections, "CORRECTION_INTERVAL_DAYS", 5)
    conn = make_db(tmp_path)
    add_problem(conn, 2, "maximum-subarray", "Maximum Subarray", intended="dp-1d")
    add_attempt(conn, 2, TODAY - timedelta(days=3), outcome="failed", pattern="prefix-sum")
    set_due(conn, 2, TODAY)

    analysis = weekly_analyze.analyze(conn, TODAY, lookahead_days=0)
    items = weekly_plan.build_plan(conn, analysis, target=10)

    assert [(i.number, reasons(i)) for i in items] == [(2, [("review", f"review due {TODAY.isoformat()}")])]
    assert [c.due for c in analysis["corrections_upcoming"]] == [TODAY + timedelta(days=2)]


def test_approach_practice_alone_is_ordered_by_due_date_then_number(tmp_path):
    conn = make_db(tmp_path)
    for number in (5, 6, 7):
        add_problem(conn, number, f"p{number}", f"Problem {number}", intended="dp-1d")
    add_attempt(conn, 7, PRACTICE_DUE_TODAY - timedelta(days=2), pattern="prefix-sum")
    add_attempt(conn, 6, PRACTICE_DUE_TODAY, pattern="prefix-sum")
    add_attempt(conn, 5, PRACTICE_DUE_TODAY, pattern="prefix-sum")

    analysis = weekly_analyze.analyze(conn, TODAY, lookahead_days=0)

    assert [i.number for i in weekly_plan.build_plan(conn, analysis, target=10)] == [7, 5, 6]


def test_a_problem_due_for_both_takes_one_slot_of_the_target(tmp_path):
    conn = make_db(tmp_path)
    add_problem(conn, 2, "maximum-subarray", "Maximum Subarray", intended="dp-1d")
    add_problem(conn, 3, "house-robber", "House Robber", intended="dp-1d")
    add_problem(conn, 4, "coin-change", "Coin Change")  # unsolved: curriculum, if a slot is left
    for number, due in ((2, TODAY - timedelta(days=1)), (3, TODAY)):
        add_attempt(conn, number, PRACTICE_DUE_TODAY, outcome="failed", pattern="prefix-sum")
        set_due(conn, number, due)

    analysis = weekly_analyze.analyze(conn, TODAY, lookahead_days=0)
    items = weekly_plan.build_plan(conn, analysis, target=2)

    assert [(i.number, [r.kind for r in i.reasons]) for i in items] == [
        (2, ["review", "re-solve"]),
        (3, ["review", "re-solve"]),
    ]
