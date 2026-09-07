import json
from datetime import date, timedelta

import pytest

from coach import db, mastery
from coach.weekly import analyze as weekly_analyze
from coach.weekly import collect as weekly_collect
from coach.weekly import plan as weekly_plan
from coach.weekly import report as weekly_report

TODAY = date(2026, 8, 31)


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
        conn.execute(
            """
            INSERT INTO enrichments (solution_id, pattern, secondary_patterns, data_structures)
            VALUES (?, ?, '[]', '[]')
            """,
            (solution_id, pattern),
        )
        # Mirrors production: tagging a solve is what makes it scorable, and the
        # enrich path recomputes right there.
        mastery.recompute_all(conn)
    return solution_id


def add_review(conn, solution_id, verdict, issues=()):
    conn.execute(
        """
        INSERT INTO reviews (solution_id, verdict, strengths, issues, time_complexity,
                             space_complexity, optimal_time_complexity, created_at)
        VALUES (?, ?, '[]', ?, 'O(n)', 'O(1)', 'O(n)', '2026-08-30')
        """,
        (
            solution_id,
            verdict,
            json.dumps([{"category": c, "description": d} for c, d in issues]),
        ),
    )
    mastery.recompute_all(conn)


def set_due(conn, number, day):
    conn.execute(
        """
        INSERT INTO review_state (problem_number, ease, interval_days, next_due, reps, lapses)
        VALUES (?, 2.5, 1.0, ?, 1, 0)
        """,
        (number, day.isoformat()),
    )


def test_collect_window_excludes_older_attempts(tmp_path):
    conn = make_db(tmp_path)
    add_problem(conn, 1, "two-sum", "Two Sum")
    add_attempt(conn, 1, TODAY - timedelta(days=2), pattern="hashmap")
    add_attempt(conn, 1, TODAY - timedelta(days=20))

    week = weekly_collect.collect(conn, TODAY)
    assert len(week["attempts"]) == 1
    assert week["distinct_problems"] == 1
    assert week["attempts"][0]["pattern"] == "hashmap"
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


def test_plan_orders_reviews_then_off_pattern_then_weak(tmp_path):
    conn = make_db(tmp_path)
    add_problem(conn, 1, "two-sum", "Two Sum", tags=["hash-table"])
    add_problem(conn, 2, "maximum-subarray", "Maximum Subarray", tags=["dynamic-programming"],
                intended="dp-1d")
    add_problem(conn, 3, "coin-change", "Coin Change", tags=["dynamic-programming"])
    add_problem(conn, 4, "house-robber", "House Robber", tags=["dynamic-programming"])
    add_attempt(conn, 1, TODAY - timedelta(days=1), pattern="hashmap")
    add_attempt(conn, 2, TODAY - timedelta(days=1), outcome="struggled", pattern="prefix-sum")
    set_due(conn, 1, TODAY)

    analysis = weekly_analyze.analyze(conn, TODAY)
    analysis["weak_patterns"] = ["dp-1d"]
    items = weekly_plan.build_plan(conn, analysis, target=10)

    assert items[0].number == 1
    assert "review due" in items[0].reason
    assert items[1].number == 2
    assert "re-solve" in items[1].reason
    weak = [i for i in items if i.reason == "weak pattern: dp-1d"]
    assert {i.number for i in weak} == {3, 4}


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
    assert all("review due" in i.reason for i in items)


def test_render_handles_empty_week(tmp_path):
    conn = make_db(tmp_path)
    add_problem(conn, 1, "two-sum", "Two Sum", tags=["hash-table"])

    week = weekly_collect.collect(conn, TODAY)
    analysis = weekly_analyze.analyze(conn, TODAY)
    text = weekly_report.render(week, analysis, None, TODAY)

    assert "# Weekly report — 2026-36" in text
    assert "No attempts logged this week" in text
    assert "LLM unavailable" in text


def test_render_includes_tables_and_narrative(tmp_path):
    conn = make_db(tmp_path)
    add_problem(conn, 1, "two-sum", "Two Sum", tags=["hash-table"], intended="hashmap")
    add_problem(conn, 2, "maximum-subarray", "Maximum Subarray", intended="dp-1d")
    add_attempt(conn, 1, TODAY - timedelta(days=1), outcome="clean", pattern="hashmap", minutes=12)
    add_attempt(conn, 2, TODAY - timedelta(days=1), outcome="struggled", pattern="prefix-sum")

    week = weekly_collect.collect(conn, TODAY)
    analysis = weekly_analyze.analyze(conn, TODAY)
    text = weekly_report.render(week, analysis, "Focus on dp-1d.", TODAY)

    assert "| 2026-08-30 | #1 Two Sum | Easy | clean | 12 | hashmap |" in text
    assert "canonical approach is **dp-1d**" in text
    assert "Focus on dp-1d." in text
    assert "blind75: 2/2" in text


def test_render_plans_nothing_and_says_where_planning_lives(tmp_path):
    """The report diagnoses the week; `coach today` picks what to solve next."""
    conn = make_db(tmp_path)
    add_problem(conn, 1, "two-sum", "Two Sum", tags=["hash-table"])
    add_problem(conn, 2, "valid-anagram", "Valid Anagram", tags=["hash-table"])
    set_due(conn, 1, TODAY)

    week = weekly_collect.collect(conn, TODAY)
    analysis = weekly_analyze.analyze(conn, TODAY)
    text = weekly_report.render(week, analysis, "Drill hashmaps.", TODAY)

    assert "Plan for next week" not in text
    assert "https://leetcode.com/problems/" not in text
    assert "coach today" in text


def test_summarize_feeds_llm_the_key_facts(tmp_path):
    conn = make_db(tmp_path)
    add_problem(conn, 1, "two-sum", "Two Sum", intended="hashmap")
    add_attempt(conn, 1, TODAY - timedelta(days=1), outcome="struggled", pattern="hashmap")

    week = weekly_collect.collect(conn, TODAY)
    analysis = weekly_analyze.analyze(conn, TODAY)
    summary = weekly_report.summarize(week, analysis)

    assert "Attempts this week: 1" in summary
    assert "#1 Two Sum" in summary
    assert "outcome=struggled" in summary
    assert "review=" not in summary


def test_summarize_carries_stored_reviews(tmp_path):
    conn = make_db(tmp_path)
    add_problem(conn, 1, "two-sum", "Two Sum")
    add_problem(conn, 2, "valid-palindrome", "Valid Palindrome")
    reviewed = add_attempt(conn, 1, TODAY - timedelta(days=1), outcome="clean", pattern="hashmap")
    add_review(
        conn,
        reviewed,
        "needs-work",
        [("edge-case", "wrong on an empty array"), ("complexity", "sorts unnecessarily")],
    )
    add_attempt(conn, 2, TODAY - timedelta(days=1), outcome="struggled", pattern="two-pointers")

    week = weekly_collect.collect(conn, TODAY)
    summary = weekly_report.summarize(week, weekly_analyze.analyze(conn, TODAY))

    reviewed_line = next(line for line in summary.splitlines() if "#1 Two Sum" in line)
    assert "review=needs-work" in reviewed_line
    assert "edge-case: wrong on an empty array" in reviewed_line
    assert "complexity: sorts unnecessarily" in reviewed_line
    # The unreviewed solve is unchanged - a missing review is not an empty one.
    assert "review=" not in next(line for line in summary.splitlines() if "#2" in line)


def test_summarize_notes_a_clean_review_without_issues(tmp_path):
    conn = make_db(tmp_path)
    add_problem(conn, 1, "two-sum", "Two Sum")
    solution_id = add_attempt(conn, 1, TODAY - timedelta(days=1), pattern="hashmap")
    add_review(conn, solution_id, "optimal")

    week = weekly_collect.collect(conn, TODAY)
    summary = weekly_report.summarize(week, weekly_analyze.analyze(conn, TODAY))

    assert "review=optimal" in summary
    assert "()" not in summary


def test_week_key_uses_iso_week():
    assert weekly_report.week_key(date(2026, 8, 31)) == "2026-36"
    assert weekly_report.week_key(date(2026, 1, 1)) == "2026-01"
