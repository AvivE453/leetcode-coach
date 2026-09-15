import json
from datetime import date, timedelta

import pytest
from conftest import tag_solution

from coach import config, corrections, db, enrich, history
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


def loaded_attempt(number, day, main_patterns=None, outcome="clean", minutes=None):
    """One loaded attempt, as history.load() would have returned it."""
    return history.Attempt(
        id=number,
        problem=history.Problem(
            number=number,
            slug=f"p{number}",
            title=f"Problem {number}",
            difficulty="Easy",
            canonical=enrich.Canonical(None, []),
        ),
        day=day,
        outcome=outcome,
        minutes=minutes,
        main_patterns=main_patterns,
        secondary_patterns=(),
        verdict=None,
        issues=(),
    )


def test_window_rows_carry_exactly_the_keys_the_weekly_table_reads():
    """/api/weekly hands these rows to weekly.js untouched, so a renamed key is a silent
    null in the browser with nothing here to fail. `date` is the ISO string, not a date."""
    week = weekly_collect.window([loaded_attempt(1, TODAY, ("hashmap",), minutes=25)], TODAY)

    assert week["attempts"] == [
        {
            "date": TODAY.isoformat(),
            "problem_number": 1,
            "title": "Problem 1",
            "difficulty": "Easy",
            "outcome": "clean",
            "minutes": 25,
            "main_patterns": ["hashmap"],
        }
    ]
    assert (week["start"], week["end"]) == (TODAY - timedelta(days=6), TODAY)


def test_window_reports_an_untagged_solve_with_no_patterns():
    """Still a solve, just one with nothing to attribute it to - and a list either way,
    because the table joins it."""
    [row] = weekly_collect.window([loaded_attempt(1, TODAY)], TODAY)["attempts"]

    assert row["main_patterns"] == []


def test_window_keeps_the_first_day_of_the_window_and_drops_the_day_before():
    attempts = [
        loaded_attempt(1, TODAY - timedelta(days=7)),
        loaded_attempt(2, TODAY - timedelta(days=6)),
    ]

    week = weekly_collect.window(attempts, TODAY)
    assert [r["problem_number"] for r in week["attempts"]] == [2]
    assert week["distinct_problems"] == 1


def test_analyze_flags_weak_and_stale_patterns(tmp_path):
    conn = make_db(tmp_path)
    add_problem(conn, 1, "two-sum", "Two Sum")
    add_problem(conn, 3, "lru-cache", "LRU Cache")
    # weak: failures across five problems, so mastery bottoms out at 1.0
    for number in range(10, 15):
        add_problem(conn, number, f"dp-{number}", f"DP {number}")
        add_attempt(conn, number, TODAY - timedelta(days=1), outcome="failed", pattern="dp-1d")
    # NOT weak: the same 100% struggle rate over five problems, but solved every time - mastery 3.0
    for number in range(20, 25):
        add_problem(conn, number, f"two-pointers-{number}", f"Two Pointers {number}")
        add_attempt(conn, number, TODAY - timedelta(days=1), outcome="struggled", pattern="two-pointers")
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


def test_analyze_needs_five_distinct_problems_before_calling_a_pattern_weak(tmp_path):
    """Attempts alone never judge a pattern. SM-2 re-queues a failed problem every few
    days, so one hard problem racks up attempts on its own - that is the problem's
    trouble, and SM-2's to handle, not a verdict on the pattern."""
    conn = make_db(tmp_path)
    for number in range(1, 6):
        add_problem(conn, number, f"problem-{number}", f"Problem {number}")
    for requeue in range(10):
        add_attempt(conn, 1, TODAY - timedelta(days=3 * requeue), outcome="failed", pattern="dp-1d")
    assert weekly_analyze.analyze(conn, TODAY)["weak_patterns"] == []

    for number in (2, 3, 4):
        add_attempt(conn, number, TODAY, outcome="failed", pattern="dp-1d")
    assert weekly_analyze.analyze(conn, TODAY)["weak_patterns"] == []

    add_attempt(conn, 5, TODAY, outcome="failed", pattern="dp-1d")
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

    A success before its review is due does not count as the review, so a four-slot
    list padded with Friday's reviews would spend slots without moving their schedules.
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


def test_analyze_keeps_approach_practice_due_by_the_lookahead_horizon(tmp_path):
    conn = make_db(tmp_path)
    add_problem(conn, 2, "maximum-subarray", "Maximum Subarray", intended="dp-1d")
    add_problem(conn, 3, "house-robber", "House Robber", intended="dp-1d")
    add_attempt(conn, 2, PRACTICE_DUE_TODAY, pattern="prefix-sum")
    add_attempt(conn, 3, TODAY, pattern="prefix-sum")  # due three days from now

    def due_by(lookahead_days):
        analysis = weekly_analyze.analyze(conn, TODAY, lookahead_days=lookahead_days)
        return [c.problem["number"] for c in analysis["corrections_due"]]

    assert due_by(0) == [2]
    assert due_by(weekly_analyze.PLAN_LOOKAHEAD_DAYS) == [2, 3]


def listed(items):
    """A heading's items as (number, reasons) pairs, in the order the plan gave them."""
    return [(i.number, reasons(i)) for i in items]


def test_plan_puts_each_rule_under_its_own_heading(tmp_path):
    """Each heading holds what its rule gave. `kind` - what the web UI styles - is set
    where the rule fires, so no wording change to a reason's text can move it."""
    conn = make_db(tmp_path)
    add_problem(conn, 1, "two-sum", "Two Sum", tags=["hash-table"])
    add_problem(conn, 2, "maximum-subarray", "Maximum Subarray", tags=["dynamic-programming"],
                intended="dp-1d")
    add_problem(conn, 3, "coin-change", "Coin Change", tags=["dynamic-programming"])
    add_problem(conn, 4, "house-robber", "House Robber", tags=["dynamic-programming"])
    add_problem(conn, 5, "valid-anagram", "Valid Anagram", tags=["string"])
    add_attempt(conn, 1, TODAY - timedelta(days=1), pattern="hashmap")
    add_attempt(conn, 2, PRACTICE_DUE_TODAY, outcome="struggled", pattern="prefix-sum")
    set_due(conn, 1, TODAY)

    analysis = weekly_analyze.analyze(conn, TODAY)
    analysis["weak_patterns"] = ["dp-1d"]
    plan = weekly_plan.build_plan(conn, analysis, limit=10)

    # #3 and #4 carry the dynamic-programming tag, so the weak dp-1d pattern claims them
    # before curriculum progression runs; only #5 is left to top up Due.
    assert listed(plan.due) == [
        (1, [("review", f"review due {TODAY.isoformat()}")]),
        (5, [("curriculum", f"{config.CURRICULUM} progression")]),
    ]
    assert listed(plan.approach) == [(2, [("re-solve", "practice an accepted approach: dp-1d")])]
    assert {i.number for i in plan.weak} == {3, 4}
    assert all(reasons(i) == [("weak-pattern", "weak pattern: dp-1d")] for i in plan.weak)
    assert (plan.reviews_owed, plan.practice_owed) == (1, 1)


def test_plan_holds_each_heading_to_the_limit_and_lists_a_problem_once(tmp_path):
    conn = make_db(tmp_path)
    for n in range(1, 10):
        add_problem(conn, n, f"p{n}", f"Problem {n}", tags=["hash-table"])
    set_due(conn, 1, TODAY)

    analysis = weekly_analyze.analyze(conn, TODAY)
    analysis["weak_patterns"] = ["hashmap"]
    plan = weekly_plan.build_plan(conn, analysis, limit=3)

    headings = [plan.due, plan.approach, plan.weak]
    numbers = [i.number for heading in headings for i in heading]
    assert [len(heading) for heading in headings] == [3, 0, 3]
    assert len(set(numbers)) == len(numbers)


@pytest.mark.parametrize("limit, progression", [(6, 2), (4, 0)])
def test_curriculum_tops_due_up_only_to_the_limit(tmp_path, limit, progression):
    """Progression is Due's filler: it takes the slots reviews leave, and none once
    reviews fill the heading."""
    conn = make_db(tmp_path)
    for n in range(1, 5):
        add_problem(conn, n, f"due-{n}", f"Due {n}")
        set_due(conn, n, TODAY)
    for n in range(10, 14):
        add_problem(conn, n, f"new-{n}", f"New {n}")

    plan = weekly_plan.build_plan(conn, weekly_analyze.analyze(conn, TODAY), limit=limit)

    assert [[r.kind for r in i.reasons] for i in plan.due] == (
        [["review"]] * 4 + [["curriculum"]] * progression
    )


def test_reviews_beyond_the_limit_stay_owed_and_off_every_heading(tmp_path):
    """Due claims every review due. One that does not fit waits for tomorrow, still among
    the most overdue - it never turns up under Approach practice without its review."""
    conn = make_db(tmp_path)
    for number, due in ((2, TODAY - timedelta(days=2)), (3, TODAY - timedelta(days=1)), (4, TODAY)):
        add_problem(conn, number, f"p{number}", f"Problem {number}", intended="dp-1d")
        add_attempt(conn, number, PRACTICE_DUE_TODAY, outcome="failed", pattern="prefix-sum")
        set_due(conn, number, due)
    add_problem(conn, 9, "coin-change", "Coin Change")  # unsolved: curriculum, if a slot were left

    analysis = weekly_analyze.analyze(conn, TODAY, lookahead_days=0)
    plan = weekly_plan.build_plan(conn, analysis, limit=2)

    assert [(i.number, [r.kind for r in i.reasons]) for i in plan.due] == [
        (2, ["review", "re-solve"]),
        (3, ["review", "re-solve"]),
    ]
    assert plan.approach == []
    assert (plan.reviews_owed, plan.practice_owed) == (3, 0)


@pytest.mark.parametrize("limit, per_pattern", [(10, [3, 3]), (4, [3, 1])])
def test_weak_patterns_share_their_heading_weakest_first(tmp_path, limit, per_pattern):
    """At most MAX_PER_WEAK_PATTERN each, so the weakest pattern cannot crowd out the rest."""
    conn = make_db(tmp_path)
    for n in range(1, 6):
        add_problem(conn, n, f"dp-{n}", f"DP {n}", tags=["dynamic-programming"])
        add_problem(conn, 10 + n, f"greedy-{n}", f"Greedy {n}", tags=["greedy"])

    analysis = weekly_analyze.analyze(conn, TODAY)
    analysis["weak_patterns"] = ["dp-1d", "greedy"]  # weakest first, as analyze() orders them
    weak = weekly_plan.build_plan(conn, analysis, limit=limit).weak

    picked = [sum(reasons(i) == [("weak-pattern", f"weak pattern: {p}")] for i in weak) for p in ("dp-1d", "greedy")]
    assert picked == per_pattern


def test_each_heading_caps_its_own_hard_new_picks(tmp_path):
    """New picks are optional, so each heading keeps to hard_cap(limit) Hard problems,
    counted apart: Hard weak picks never use up the curriculum fill's allowance."""
    conn = make_db(tmp_path)
    for n in range(1, 11):
        add_problem(conn, n, f"h{n}", f"Hard {n}", difficulty="Hard", tags=["dynamic-programming"])
    add_problem(conn, 20, "easy-one", "Easy One", difficulty="Easy")

    analysis = weekly_analyze.analyze(conn, TODAY)
    analysis["weak_patterns"] = ["dp-1d"]
    plan = weekly_plan.build_plan(conn, analysis, limit=10)

    assert weekly_plan.hard_cap(10) == 2
    assert [i.difficulty for i in plan.weak] == ["Hard", "Hard"]
    assert sorted(i.difficulty for i in plan.due) == ["Easy", "Hard", "Hard"]


def test_plan_keeps_due_reviews_even_when_hard(tmp_path):
    conn = make_db(tmp_path)
    for n in range(1, 6):
        add_problem(conn, n, f"h{n}", f"Hard {n}", difficulty="Hard")
        set_due(conn, n, TODAY)

    analysis = weekly_analyze.analyze(conn, TODAY)
    due = weekly_plan.build_plan(conn, analysis, limit=10).due
    assert len(due) == 5
    assert all(reasons(i) == [("review", f"review due {TODAY.isoformat()}")] for i in due)


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

    plan = weekly_plan.build_plan(conn, weekly_analyze.analyze(conn, TODAY), limit=10)

    assert {i.number: reasons(i) for i in plan.due} == {
        1: [("review", "re-solve: review reported an edge-case failure")],
        2: [("review", f"review due {TODAY.isoformat()}")],
    }


def test_a_problem_owing_a_review_and_approach_practice_is_one_item_under_due(tmp_path):
    """The old dedupe kept the review's sentence and silently dropped the approach to use."""
    conn = make_db(tmp_path)
    add_problem(conn, 2, "maximum-subarray", "Maximum Subarray", intended="dp-1d")
    solution_id = add_attempt(conn, 2, PRACTICE_DUE_TODAY, pattern="prefix-sum")
    add_review(conn, solution_id, "needs-work", "bug")
    set_due(conn, 2, TODAY)

    analysis = weekly_analyze.analyze(conn, TODAY, lookahead_days=0)
    plan = weekly_plan.build_plan(conn, analysis, limit=10)

    assert [c.problem["number"] for c in analysis["corrections_due"]] == [2]  # due by both rules
    assert listed(plan.due) == [
        (
            2,
            [
                ("review", "re-solve: review reported a bug"),
                ("re-solve", "practice an accepted approach: dp-1d"),
            ],
        )
    ]
    assert (plan.approach, plan.practice_owed) == ([], 0)


@pytest.mark.parametrize("days_ago, planned", [(2, []), (3, [2])])
def test_approach_practice_joins_the_plan_on_its_due_date_and_not_before(
    tmp_path, days_ago, planned
):
    """Practising a problem, however it went, must not bring it straight back: approach
    practice waits CORRECTION_INTERVAL_DAYS, and is owed from exactly that day."""
    conn = make_db(tmp_path)
    add_problem(conn, 2, "maximum-subarray", "Maximum Subarray", intended="dp-1d")
    add_attempt(conn, 2, TODAY - timedelta(days=days_ago), pattern="prefix-sum")

    analysis = weekly_analyze.analyze(conn, TODAY, lookahead_days=0)

    assert [i.number for i in weekly_plan.build_plan(conn, analysis, limit=10).approach] == planned
    # Kept off the plan while it waits, never dropped: the problem owes it either way.
    assert [c.problem["number"] for c in corrections.outstanding(conn)] == [2]


def test_a_review_due_before_its_approach_practice_carries_only_its_own_reason(tmp_path):
    """Approach practice counts from the latest attempt, but a success before the review is
    due leaves the review where it was. Solved off-pattern a week ago and again yesterday:
    the review is due today and is listed alone, while the approach practice waits for its
    own date rather than riding along early."""
    conn = make_db(tmp_path)
    add_problem(conn, 2, "maximum-subarray", "Maximum Subarray", intended="dp-1d")
    add_attempt(conn, 2, TODAY - timedelta(days=7), pattern="prefix-sum")
    add_attempt(conn, 2, TODAY - timedelta(days=1), pattern="prefix-sum")
    set_due(conn, 2, TODAY)  # where the replay leaves it: yesterday's clean solve was early

    analysis = weekly_analyze.analyze(conn, TODAY, lookahead_days=0)
    plan = weekly_plan.build_plan(conn, analysis, limit=10)

    assert listed(plan.due) == [(2, [("review", f"review due {TODAY.isoformat()}")])]
    assert plan.approach == []
    assert [c.due for c in corrections.outstanding(conn)] == [TODAY + timedelta(days=2)]


def test_approach_practice_is_ordered_by_due_date_and_held_to_the_limit(tmp_path):
    conn = make_db(tmp_path)
    for number in (5, 6, 7):
        add_problem(conn, number, f"p{number}", f"Problem {number}", intended="dp-1d")
    add_attempt(conn, 7, PRACTICE_DUE_TODAY - timedelta(days=2), pattern="prefix-sum")
    add_attempt(conn, 6, PRACTICE_DUE_TODAY, pattern="prefix-sum")
    add_attempt(conn, 5, PRACTICE_DUE_TODAY, pattern="prefix-sum")

    analysis = weekly_analyze.analyze(conn, TODAY, lookahead_days=0)

    assert [i.number for i in weekly_plan.build_plan(conn, analysis, limit=10).approach] == [7, 5, 6]
    held = weekly_plan.build_plan(conn, analysis, limit=2)
    assert ([i.number for i in held.approach], held.practice_owed) == ([7, 5], 3)
