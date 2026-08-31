import json
from datetime import date, timedelta

import numpy as np
from typer.testing import CliRunner

from coach import config, db, embed, enrich, review
from coach.cli import app

runner = CliRunner()

CODE = "class Solution:\n    def twoSum(self, nums, target):\n        return []\n"


def setup_env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "coach.db")
    monkeypatch.setattr(config, "SOLUTIONS_DIR", tmp_path / "solutions")
    monkeypatch.setattr(config, "REPORTS_DIR", tmp_path / "reports")
    conn = db.connect()
    db.init_schema(conn)
    db.upsert_problems(
        conn,
        [
            {
                "number": 1,
                "slug": "two-sum",
                "title": "Two Sum",
                "difficulty": "Easy",
                "official_tags": '["array"]',
                "paid_only": 0,
            }
        ],
    )
    conn.close()


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
    assert state["next_due"] == (date.today() + timedelta(days=1)).isoformat()

    sol_file = tmp_path / "solutions" / "0001-two-sum.py"
    assert sol_file.exists()
    content = sol_file.read_text()
    assert "# 1. Two Sum" in content
    assert "twoSum" in content


def test_second_solve_appends_and_advances_schedule(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)

    runner.invoke(app, ["log", "1", "--outcome", "clean"], input=CODE)
    result = runner.invoke(app, ["log", "1", "--outcome", "clean"], input=CODE)
    assert result.exit_code == 0, result.output

    conn = db.connect()
    assert conn.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 2
    state = conn.execute("SELECT * FROM review_state").fetchone()
    assert state["reps"] == 2
    assert state["interval_days"] == 6.0

    content = (tmp_path / "solutions" / "0001-two-sum.py").read_text()
    assert content.count("# ---") == 2


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
    secondary_patterns=[],
    data_structures=["dict"],
    key_trick="Store complements while scanning once.",
    time_complexity="O(n)",
    space_complexity="O(n)",
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

    conn = db.connect()
    row = conn.execute("SELECT intended_pattern FROM problems WHERE number = 1").fetchone()
    assert row["intended_pattern"] == "dp-1d"


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
    assert "prefix-sum: 1 attempt(s), 1 not clean" in result.output
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

    feedback = review.Review(
        issues=[review.Issue(category="bug", description="Always returns [].")],
        time_complexity="O(n)",
        space_complexity="O(n)",
        optimal_time_complexity="O(n)",
        better_approach=None,
        verdict="needs-work",
    )
    monkeypatch.setattr("coach.llm.parse", lambda prompt, output_format, **kw: feedback)

    result = runner.invoke(app, ["review", "1"])
    assert result.exit_code == 0, result.output
    assert "Verdict: needs-work" in result.output
    assert "[bug] Always returns []." in result.output


def test_review_without_solution_fails(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)
    result = runner.invoke(app, ["review", "1"])
    assert result.exit_code == 1
    assert "No stored solution" in result.output


def test_weekly_writes_report_and_records_run(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)
    monkeypatch.setattr("coach.llm.parse", lambda prompt, output_format, **kw: ENRICHMENT)
    monkeypatch.setattr("coach.embed.encode", fake_encode)
    runner.invoke(app, ["log", "1", "--outcome", "struggled"], input=CODE)
    monkeypatch.setattr("coach.llm.text", lambda prompt, **kw: "Drill hashmap problems.")

    result = runner.invoke(app, ["weekly", "--target", "5"])
    assert result.exit_code == 0, result.output

    week = date.today().isocalendar()
    path = tmp_path / "reports" / f"{week.year}-{week.week:02d}.md"
    assert path.exists()
    text = path.read_text()
    assert "#1 Two Sum" in text
    assert "Drill hashmap problems." in text

    conn = db.connect()
    run = conn.execute("SELECT * FROM weekly_runs").fetchone()
    assert run["degraded"] == 0
    assert json.loads(run["stats"])["attempts"] == 1


def test_weekly_degrades_without_llm(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)

    result = runner.invoke(app, ["weekly"])
    assert result.exit_code == 0, result.output
    assert "Narrative skipped" in result.output
    assert "degraded" in result.output

    conn = db.connect()
    run = conn.execute("SELECT * FROM weekly_runs").fetchone()
    assert run["degraded"] == 1

    week = date.today().isocalendar()
    text = (tmp_path / "reports" / f"{week.year}-{week.week:02d}.md").read_text()
    assert "No attempts logged this week" in text
    assert "LLM unavailable" in text


def test_weekly_no_llm_flag_skips_the_call(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)

    def explode(*args, **kwargs):
        raise AssertionError("--no-llm must not call the API")

    monkeypatch.setattr("coach.llm.text", explode)
    result = runner.invoke(app, ["weekly", "--no-llm"])
    assert result.exit_code == 0, result.output
    assert "degraded" in result.output


def test_weekly_without_catalog_points_at_init(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "coach.db")
    monkeypatch.setattr(config, "REPORTS_DIR", tmp_path / "reports")
    conn = db.connect()
    db.init_schema(conn)
    conn.close()

    result = runner.invoke(app, ["weekly"])
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
