import json
from datetime import date, timedelta

import numpy as np
from conftest import CODE, seed_db
from typer.testing import CliRunner

from coach import db, embed, enrich, mastery, review
from coach.cli import app

runner = CliRunner()


def setup_env(tmp_path, monkeypatch):
    """Seed the scratch database and let go of it - every CLI command opens its own."""
    seed_db(tmp_path, monkeypatch).close()


def test_log_stores_attempt_solution_and_schedule(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)

    result = runner.invoke(app, ["log", "1", "--outcome", "struggled", "--time", "25"], input=CODE)
    assert result.exit_code == 0, result.output

    conn = db.connect()
    attempt = conn.execute("SELECT * FROM attempts").fetchone()
    assert attempt["outcome"] == "struggled"
    assert attempt["minutes"] == 25

    solution = conn.execute("SELECT * FROM solutions").fetchone()
    assert "twoSum" in solution["code"]
    assert solution["attempt_id"] == attempt["id"]

    state = conn.execute("SELECT * FROM review_state").fetchone()
    assert state["next_due"] == (date.today() + timedelta(days=7)).isoformat()


def test_second_solve_appends_and_advances_schedule(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)

    runner.invoke(app, ["log", "1", "--outcome", "clean"], input=CODE)
    result = runner.invoke(app, ["log", "1", "--outcome", "clean"], input=CODE)
    assert result.exit_code == 0, result.output

    conn = db.connect()
    assert conn.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 2
    state = conn.execute("SELECT * FROM review_state").fetchone()
    assert state["reps"] == 2
    assert state["interval_days"] == 14.0


def test_log_unknown_problem_fails(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)
    result = runner.invoke(app, ["log", "99999"], input=CODE)
    assert result.exit_code == 1
    assert "not found" in result.output


def test_log_empty_input_fails(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)
    result = runner.invoke(app, ["log", "1"], input="  \n")
    assert result.exit_code == 1

    conn = db.connect()
    assert conn.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0


ENRICHMENT = enrich.Enrichment(
    pattern="hashmap",
    intended_pattern="hashmap",
    intended_secondary_patterns=["two-pointers"],
    secondary_patterns=[],
    data_structures=["dict"],
    key_trick="Store complements while scanning once.",
    time_complexity="O(n)",
    space_complexity="O(n)",
)


FEEDBACK = review.Review(
    strengths=["Uses a dict for O(1) lookups."],
    issues=[review.Issue(category="bug", description="Always returns [].")],
    time_complexity="O(n)",
    space_complexity="O(n)",
    optimal_time_complexity="O(n)",
    better_approach=None,
    verdict="needs-work",
)


def fake_encode(texts):
    vector = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    return np.tile(vector, (len(texts), 1))


def test_log_without_key_skips_enrichment(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)

    result = runner.invoke(app, ["log", "1"], input=CODE)
    assert result.exit_code == 0, result.output
    assert "Enrichment skipped" in result.output

    conn = db.connect()
    assert conn.execute("SELECT COUNT(*) FROM enrichments").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM solutions").fetchone()[0] == 1


def test_log_with_mocked_llm_enriches_and_embeds(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)
    monkeypatch.setattr("coach.llm.parse", lambda prompt, output_format, **kw: ENRICHMENT)
    monkeypatch.setattr("coach.embed.encode", fake_encode)

    result = runner.invoke(app, ["log", "1"], input=CODE)
    assert result.exit_code == 0, result.output
    assert "Pattern: hashmap" in result.output

    conn = db.connect()
    row = conn.execute("SELECT * FROM enrichments").fetchone()
    assert row["pattern"] == "hashmap"
    assert conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0] == 1


def test_log_flags_off_pattern_solve(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)
    off = ENRICHMENT.model_copy(update={"pattern": "prefix-sum", "intended_pattern": "dp-1d"})
    monkeypatch.setattr("coach.llm.parse", lambda prompt, output_format, **kw: off)
    monkeypatch.setattr("coach.embed.encode", fake_encode)

    result = runner.invoke(app, ["log", "1"], input=CODE)
    assert result.exit_code == 0, result.output
    assert "canonical approach is dp-1d" in result.output
    # both signals speak when a solve is genuinely off-pattern: the warning names
    # the central approach, the note lists every canonical route left unpractised
    assert "This problem can also be solved with: dp-1d, two-pointers" in result.output

    conn = db.connect()
    row = conn.execute("SELECT * FROM problems WHERE number = 1").fetchone()
    assert row["intended_pattern"] == "dp-1d"
    assert json.loads(row["intended_secondary_patterns"]) == ["two-pointers"]


def test_log_notes_other_canonical_approaches_without_warning(tmp_path, monkeypatch):
    """A canonical solve is never flagged, but the road not taken is still shown."""
    setup_env(tmp_path, monkeypatch)
    monkeypatch.setattr("coach.llm.parse", lambda prompt, output_format, **kw: ENRICHMENT)
    monkeypatch.setattr("coach.embed.encode", fake_encode)

    result = runner.invoke(app, ["log", "1"], input=CODE)
    assert result.exit_code == 0, result.output
    assert "This problem can also be solved with: two-pointers" in result.output
    assert "canonical approach" not in result.output


def test_review_notes_other_canonical_approaches(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)
    monkeypatch.setattr("coach.llm.parse", lambda prompt, output_format, **kw: ENRICHMENT)
    monkeypatch.setattr("coach.embed.encode", fake_encode)
    runner.invoke(app, ["log", "1"], input=CODE)

    monkeypatch.setattr("coach.llm.parse", lambda prompt, output_format, **kw: FEEDBACK)
    result = runner.invoke(app, ["review", "1"])

    assert result.exit_code == 0, result.output
    assert "This problem can also be solved with: two-pointers" in result.output


def test_log_withholds_a_standing_verdict_on_a_first_solve(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)
    monkeypatch.setattr("coach.llm.parse", lambda prompt, output_format, **kw: ENRICHMENT)
    monkeypatch.setattr("coach.embed.encode", fake_encode)

    result = runner.invoke(app, ["log", "1", "--outcome", "struggled"], input=CODE)
    assert result.exit_code == 0, result.output
    assert "too early to call" in result.output


def test_log_calls_out_a_weak_pattern(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)
    monkeypatch.setattr("coach.llm.parse", lambda prompt, output_format, **kw: ENRICHMENT)
    monkeypatch.setattr("coach.embed.encode", fake_encode)

    for _ in range(4):
        runner.invoke(app, ["log", "1", "--outcome", "failed"], input=CODE)
    result = runner.invoke(app, ["log", "1", "--outcome", "failed"], input=CODE)

    assert result.exit_code == 0, result.output
    assert "Standing: hashmap is WEAK" in result.output
    assert "mastery 1.0/5" in result.output
    assert "100% struggle rate over 5 attempts" in result.output


def test_log_reports_a_healthy_pattern_as_on_track(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)
    monkeypatch.setattr("coach.llm.parse", lambda prompt, output_format, **kw: ENRICHMENT)
    monkeypatch.setattr("coach.embed.encode", fake_encode)

    for _ in range(5):
        result = runner.invoke(app, ["log", "1", "--outcome", "clean"], input=CODE)

    assert "Standing: hashmap is on track" in result.output
    assert "mastery 5.0/5" in result.output


def test_log_holds_off_on_a_pattern_that_struggles_without_failing(tmp_path, monkeypatch):
    """The gradient's point: five shaky solves are not five failures."""
    setup_env(tmp_path, monkeypatch)
    monkeypatch.setattr("coach.llm.parse", lambda prompt, output_format, **kw: ENRICHMENT)
    monkeypatch.setattr("coach.embed.encode", fake_encode)

    for _ in range(5):
        result = runner.invoke(app, ["log", "1", "--outcome", "struggled"], input=CODE)

    assert "Standing: hashmap is on track" in result.output
    assert "mastery 3.0/5" in result.output
    assert "100% struggle rate" in result.output  # the old rule would have called this weak


def test_log_without_key_prints_no_standing(tmp_path, monkeypatch):
    """Skipped enrichment means no pattern, so there is nothing to stand on."""
    setup_env(tmp_path, monkeypatch)

    result = runner.invoke(app, ["log", "1"], input=CODE)
    assert "Standing:" not in result.output


def test_log_matching_pattern_has_no_canonical_note(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)
    monkeypatch.setattr("coach.llm.parse", lambda prompt, output_format, **kw: ENRICHMENT)
    monkeypatch.setattr("coach.embed.encode", fake_encode)

    result = runner.invoke(app, ["log", "1"], input=CODE)
    assert "canonical approach" not in result.output


def test_stats_shows_both_pattern_layers(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)
    off = ENRICHMENT.model_copy(update={"pattern": "prefix-sum", "intended_pattern": "dp-1d"})
    monkeypatch.setattr("coach.llm.parse", lambda prompt, output_format, **kw: off)
    monkeypatch.setattr("coach.embed.encode", fake_encode)
    runner.invoke(app, ["log", "1", "--outcome", "struggled"], input=CODE)

    result = runner.invoke(app, ["stats"])
    assert result.exit_code == 0, result.output
    assert "prefix-sum: mastery 3.0/5, 1 attempt(s), 1 not clean" in result.output
    assert "#1 Two Sum -> dp-1d" in result.output


def test_enrich_backfills_tags_and_embeddings(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)
    runner.invoke(app, ["log", "1"], input=CODE)  # no key -> logged without enrichment

    monkeypatch.setattr("coach.llm.parse", lambda prompt, output_format, **kw: ENRICHMENT)
    monkeypatch.setattr("coach.embed.encode", fake_encode)
    result = runner.invoke(app, ["enrich"])
    assert result.exit_code == 0, result.output
    assert "Enriched 1/1" in result.output
    assert "Embedded 1" in result.output

    conn = db.connect()
    assert conn.execute("SELECT COUNT(*) FROM enrichments").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0] == 1


def test_similar_by_number(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)
    conn = db.connect()
    db.upsert_problems(
        conn,
        [
            {
                "number": 15,
                "slug": "3sum",
                "title": "3Sum",
                "difficulty": "Medium",
                "official_tags": "[]",
                "paid_only": 0,
            }
        ],
    )
    for number, vector in [(1, [1.0, 0.0]), (15, [0.8, 0.6])]:
        solution_id = conn.execute(
            "INSERT INTO solutions (problem_number, code, created_at) VALUES (?, 'c', '2026-01-01')",
            (number,),
        ).lastrowid
        conn.execute(
            "INSERT INTO enrichments (solution_id, pattern) VALUES (?, 'hashmap')", (solution_id,)
        )
        embed.store(conn, solution_id, np.array(vector, dtype=np.float32))
    conn.commit()
    conn.close()

    result = runner.invoke(app, ["similar", "1"])
    assert result.exit_code == 0, result.output
    assert "#15 3Sum" in result.output
    assert "#1 Two Sum" not in result.output  # the query problem itself is excluded


def test_review_prints_feedback(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)
    runner.invoke(app, ["log", "1"], input=CODE)

    monkeypatch.setattr("coach.llm.parse", lambda prompt, output_format, **kw: FEEDBACK)

    result = runner.invoke(app, ["review", "1"])
    assert result.exit_code == 0, result.output
    assert "Verdict: needs-work" in result.output
    assert "[bug] Always returns []." in result.output
    assert "What went well:" in result.output
    assert "+ Uses a dict for O(1) lookups." in result.output


def test_review_is_stored_and_reused(tmp_path, monkeypatch):
    """The second look must not cost another call - that is the point of storing it."""
    setup_env(tmp_path, monkeypatch)
    runner.invoke(app, ["log", "1"], input=CODE)

    calls = []

    def counted(prompt, output_format, **kw):
        calls.append(prompt)
        return FEEDBACK

    monkeypatch.setattr("coach.llm.parse", counted)

    runner.invoke(app, ["review", "1"])
    second = runner.invoke(app, ["review", "1"])

    assert len(calls) == 1
    assert "(stored review" in second.output
    assert "Verdict: needs-work" in second.output

    third = runner.invoke(app, ["review", "1", "--refresh"])
    assert len(calls) == 2
    assert "(stored review" not in third.output


def test_review_without_solution_fails(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)
    result = runner.invoke(app, ["review", "1"])
    assert result.exit_code == 1
    assert "No stored solution" in result.output


def test_review_without_key_degrades(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)
    runner.invoke(app, ["log", "1"], input=CODE)

    result = runner.invoke(app, ["review", "1"])
    assert result.exit_code == 1
    assert "Review unavailable" in result.output
    assert "ANTHROPIC_API_KEY" in result.output


def test_weekly_lists_the_week_and_how_each_pattern_is_going(tmp_path, monkeypatch):
    """The live view: no report file, no stored run, no API call anywhere in it."""
    setup_env(tmp_path, monkeypatch)
    monkeypatch.setattr("coach.llm.parse", lambda prompt, output_format, **kw: ENRICHMENT)
    monkeypatch.setattr("coach.embed.encode", fake_encode)
    runner.invoke(app, ["log", "1", "--outcome", "struggled"], input=CODE)

    result = runner.invoke(app, ["weekly"])
    assert result.exit_code == 0, result.output

    assert "1 attempt(s) on 1 problem(s)" in result.output
    assert "#1 Two Sum" in result.output
    assert "struggled" in result.output
    # One attempt is far below WEAK_MIN_ATTEMPTS, so nothing is claimed either way.
    assert "hashmap: too early to call" in result.output
    assert not (tmp_path / "reports").exists()


def test_weekly_calls_a_pattern_weak_and_shows_the_week_movement(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)
    conn = db.connect()
    # Five failures before this week bottom the score out at 1.0; a clean solve
    # inside the window lifts it, which is exactly what the trend must report.
    for day in range(12, 7, -1):
        add_scored_attempt(conn, date.today() - timedelta(days=day), "failed")
    add_scored_attempt(conn, date.today(), "clean")
    conn.close()

    result = runner.invoke(app, ["weekly"])
    assert result.exit_code == 0, result.output

    line = next(ln for ln in result.output.splitlines() if "hashmap:" in ln)
    assert "WEAK" in line
    assert "+0.8 since last week" in line  # 1.0 -> 1.8 on one clean solve
    assert "1 this week, 6 all-time" in line


def test_weekly_without_catalog_points_at_init(tmp_path, monkeypatch):
    seed_db(tmp_path, monkeypatch, []).close()  # schema, but no catalog

    result = runner.invoke(app, ["weekly"])
    assert result.exit_code == 1
    assert "coach init" in result.output


def add_curriculum_problems(conn):
    """Three more blind75 problems, so the daily plan has curriculum slots to fill.

    Slugs and order match coach/curriculum/blind75.json, which build_plan sorts by.
    """
    db.upsert_problems(
        conn,
        [
            {"number": 217, "slug": "contains-duplicate", "title": "Contains Duplicate",
             "difficulty": "Easy", "official_tags": '["array"]', "paid_only": 0},
            {"number": 242, "slug": "valid-anagram", "title": "Valid Anagram",
             "difficulty": "Easy", "official_tags": '["string"]', "paid_only": 0},
            {"number": 49, "slug": "group-anagrams", "title": "Group Anagrams",
             "difficulty": "Medium", "official_tags": '["string"]', "paid_only": 0},
        ],
    )
    conn.execute("UPDATE problems SET in_blind75 = 1")
    conn.commit()


def add_scored_attempt(conn, day, outcome, pattern="hashmap"):
    """One enriched solve of #1, scored - the history a mastery number folds over."""
    attempt_id = conn.execute(
        "INSERT INTO attempts (problem_number, date, outcome) VALUES (1, ?, ?)",
        (day.isoformat(), outcome),
    ).lastrowid
    solution_id = conn.execute(
        "INSERT INTO solutions (problem_number, attempt_id, code, created_at) VALUES (1, ?, 'c', ?)",
        (attempt_id, day.isoformat()),
    ).lastrowid
    conn.execute(
        """
        INSERT INTO enrichments (solution_id, pattern, secondary_patterns, data_structures)
        VALUES (?, ?, '[]', '[]')
        """,
        (solution_id, pattern),
    )
    conn.commit()
    mastery.recompute_all(conn)


def test_today_lists_due_reviews_before_curriculum_and_respects_target(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)
    conn = db.connect()
    add_curriculum_problems(conn)
    conn.execute(
        """
        INSERT INTO review_state (problem_number, ease, interval_days, next_due, reps, lapses)
        VALUES (49, 2.5, 7.0, ?, 1, 0)
        """,
        (date.today().isoformat(),),
    )
    conn.commit()
    conn.close()

    result = runner.invoke(app, ["today", "--target", "3"])
    assert result.exit_code == 0, result.output

    lines = [ln for ln in result.output.splitlines() if ln.startswith("  #")]
    assert len(lines) == 3
    assert "#49 Group Anagrams" in lines[0]
    assert "review due" in lines[0]
    # then curriculum order from blind75.json: contains-duplicate, valid-anagram
    assert "#217 Contains Duplicate" in lines[1]
    assert "#242 Valid Anagram" in lines[2]


def test_today_ignores_reviews_that_are_not_due_yet(tmp_path, monkeypatch):
    """The daily list means today: solving a review early re-anchors SM-2 from
    today and shortens the interval, so Friday's review must not appear now."""
    setup_env(tmp_path, monkeypatch)
    conn = db.connect()
    conn.execute(
        """
        INSERT INTO review_state (problem_number, ease, interval_days, next_due, reps, lapses)
        VALUES (1, 2.5, 7.0, ?, 1, 0)
        """,
        ((date.today() + timedelta(days=3)).isoformat(),),
    )
    conn.commit()
    conn.close()

    today_out = runner.invoke(app, ["today"])
    assert today_out.exit_code == 0, today_out.output
    assert "Nothing to do today" in today_out.output


def test_today_drops_a_problem_once_it_is_solved(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)
    conn = db.connect()
    add_curriculum_problems(conn)
    conn.close()

    assert "#1 Two Sum" in runner.invoke(app, ["today"]).output

    runner.invoke(app, ["log", "1", "--outcome", "clean"], input=CODE)

    after = runner.invoke(app, ["today"])
    assert after.exit_code == 0, after.output
    assert "#1 Two Sum" not in after.output
    assert "#217 Contains Duplicate" in after.output


def test_today_never_calls_the_llm_and_writes_nothing(tmp_path, monkeypatch):
    """The daily list is pure SQL. It used to also generate the week's report on
    the first run of an ISO week, which is the one thing that ever cost money;
    now every run of every week is free, so a fresh database is the test."""
    setup_env(tmp_path, monkeypatch)
    conn = db.connect()
    add_curriculum_problems(conn)
    conn.close()

    def explode(*args, **kwargs):
        raise AssertionError("the daily list must not call the API")

    monkeypatch.setattr("coach.llm.parse", explode)

    result = runner.invoke(app, ["today"])
    assert result.exit_code == 0, result.output
    assert "problem(s) for today" in result.output
    assert "weekly review" not in result.output
    assert not (tmp_path / "reports").exists()


def test_today_without_catalog_points_at_init(tmp_path, monkeypatch):
    seed_db(tmp_path, monkeypatch, []).close()  # schema, but no catalog

    result = runner.invoke(app, ["today"])
    assert result.exit_code == 1
    assert "coach init" in result.output


def test_due_lists_overdue_problems(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)
    runner.invoke(app, ["log", "1", "--outcome", "clean"], input=CODE)

    conn = db.connect()
    conn.execute(
        "UPDATE review_state SET next_due = ?",
        ((date.today() - timedelta(days=2)).isoformat(),),
    )
    conn.commit()
    conn.close()

    result = runner.invoke(app, ["due"])
    assert result.exit_code == 0
    assert "#1 Two Sum" in result.output
    assert "overdue 2d" in result.output
