import json
from datetime import date, timedelta

from coach import db
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
    return attempt_id


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
    # weak: 2 of 3 attempts not clean
    for outcome in ["struggled", "failed", "clean"]:
        add_attempt(conn, 2, TODAY - timedelta(days=1), outcome=outcome, pattern="dp-1d")
    # strong: single clean attempt
    add_attempt(conn, 1, TODAY - timedelta(days=1), outcome="clean", pattern="hashmap")
    # stale: clean but 60 days ago
    add_attempt(conn, 3, TODAY - timedelta(days=60), outcome="clean", pattern="design")

    analysis = weekly_analyze.analyze(conn, TODAY)
    assert analysis["weak_patterns"] == ["dp-1d"]
    assert analysis["stale_patterns"] == ["design"]
    rates = {p["pattern"]: p["struggle_rate"] for p in analysis["patterns"]}
    assert rates["dp-1d"] > 0.6
    assert rates["hashmap"] == 0.0


def test_analyze_reports_due_and_curriculum(tmp_path):
    conn = make_db(tmp_path)
    add_problem(conn, 1, "two-sum", "Two Sum")
    add_problem(conn, 2, "coin-change", "Coin Change")
    add_attempt(conn, 1, TODAY - timedelta(days=1), pattern="hashmap")
    set_due(conn, 1, TODAY - timedelta(days=1))
    set_due(conn, 2, TODAY + timedelta(days=30))  # outside the 7-day horizon

    analysis = weekly_analyze.analyze(conn, TODAY)
    assert [r["number"] for r in analysis["due"]] == [1]
    assert analysis["curriculum"]["blind75"] == (1, 2)


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
    items = weekly_plan.build_plan(conn, analysis, target=5)
    text = weekly_report.render(week, analysis, items, None, TODAY)

    assert "# Weekly report — 2026-36" in text
    assert "No attempts logged this week" in text
    assert "LLM unavailable" in text
    assert "https://leetcode.com/problems/two-sum/" in text


def test_render_includes_tables_and_narrative(tmp_path):
    conn = make_db(tmp_path)
    add_problem(conn, 1, "two-sum", "Two Sum", tags=["hash-table"], intended="hashmap")
    add_problem(conn, 2, "maximum-subarray", "Maximum Subarray", intended="dp-1d")
    add_attempt(conn, 1, TODAY - timedelta(days=1), outcome="clean", pattern="hashmap", minutes=12)
    add_attempt(conn, 2, TODAY - timedelta(days=1), outcome="struggled", pattern="prefix-sum")

    week = weekly_collect.collect(conn, TODAY)
    analysis = weekly_analyze.analyze(conn, TODAY)
    items = weekly_plan.build_plan(conn, analysis, target=5)
    text = weekly_report.render(week, analysis, items, "Focus on dp-1d.", TODAY)

    assert "| 2026-08-30 | #1 Two Sum | Easy | clean | 12 | hashmap |" in text
    assert "canonical approach is **dp-1d**" in text
    assert "Focus on dp-1d." in text
    assert "blind75: 2/2" in text


def test_summarize_feeds_llm_the_key_facts(tmp_path):
    conn = make_db(tmp_path)
    add_problem(conn, 1, "two-sum", "Two Sum", intended="hashmap")
    add_attempt(conn, 1, TODAY - timedelta(days=1), outcome="struggled", pattern="hashmap")

    week = weekly_collect.collect(conn, TODAY)
    analysis = weekly_analyze.analyze(conn, TODAY)
    summary = weekly_report.summarize(week, analysis, [])

    assert "Attempts this week: 1" in summary
    assert "#1 Two Sum" in summary
    assert "outcome=struggled" in summary


def test_week_key_uses_iso_week():
    assert weekly_report.week_key(date(2026, 8, 31)) == "2026-36"
    assert weekly_report.week_key(date(2026, 1, 1)) == "2026-01"
