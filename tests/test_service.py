import importlib
from datetime import date

import numpy as np
import pytest

from coach import config, db, embed, enrich, review, service

CODE = "class Solution:\n    def twoSum(self, nums, target):\n        return []\n"

ENRICHMENT = enrich.Enrichment(
    pattern="hashmap",
    intended_pattern="hashmap",
    # Two Sum really does have a second canonical route (sort + two-pointers), so
    # every fixture carries one - the empty case would not exercise much.
    intended_secondary_patterns=["two-pointers"],
    secondary_patterns=[],
    data_structures=["dict"],
    key_trick="Store complements while scanning once.",
    time_complexity="O(n)",
    space_complexity="O(n)",
)


FEEDBACK = review.Review(
    strengths=[],
    issues=[review.Issue(category="bug", description="Always returns [].")],
    time_complexity="O(n)",
    space_complexity="O(n)",
    optimal_time_complexity="O(n)",
    better_approach=None,
    verdict="needs-work",
)


def fake_encode(texts):
    return np.tile(np.array([1.0, 0.0, 0.0], dtype=np.float32), (len(texts), 1))


def setup_env(tmp_path, monkeypatch, problems=None):
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "coach.db")
    monkeypatch.setattr(config, "REPORTS_DIR", tmp_path / "reports")
    conn = db.connect()
    db.init_schema(conn)
    db.upsert_problems(
        conn,
        problems
        or [
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
    return conn


def test_log_solve_stores_attempt_solution_and_schedule(tmp_path, monkeypatch):
    conn = setup_env(tmp_path, monkeypatch)

    result = service.log_solve(conn, 1, "struggled", CODE, minutes=25, today=date(2026, 9, 1))

    assert result.title == "Two Sum"
    assert result.next_due == date(2026, 9, 2)
    assert conn.execute("SELECT minutes FROM attempts").fetchone()["minutes"] == 25
    assert conn.execute("SELECT code FROM solutions").fetchone()["code"].startswith("class Solution")


def test_log_solve_rejects_unknown_problem_and_empty_code(tmp_path, monkeypatch):
    conn = setup_env(tmp_path, monkeypatch)

    with pytest.raises(service.ProblemNotFound):
        service.log_solve(conn, 99999, "clean", CODE)
    with pytest.raises(service.EmptySolution):
        service.log_solve(conn, 1, "clean", "   \n ")
    assert conn.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0


def test_enrich_solution_now_reports_llm_degradation(tmp_path, monkeypatch):
    conn = setup_env(tmp_path, monkeypatch)
    result = service.log_solve(conn, 1, "clean", CODE)
    problem = service.get_problem(conn, 1)

    e = service.enrich_solution_now(conn, result.solution_id, problem, CODE)

    assert e.pattern is None
    assert "ANTHROPIC_API_KEY" in e.skipped
    assert conn.execute("SELECT COUNT(*) FROM enrichments").fetchone()[0] == 0


def test_enrich_solution_now_reports_embedding_degradation(tmp_path, monkeypatch):
    conn = setup_env(tmp_path, monkeypatch)
    monkeypatch.setattr("coach.llm.parse", lambda prompt, output_format, **kw: ENRICHMENT)

    def no_embeddings(texts):
        raise embed.EmbeddingsUnavailable("sentence-transformers not installed")

    monkeypatch.setattr("coach.embed.encode", no_embeddings)
    result = service.log_solve(conn, 1, "clean", CODE)

    e = service.enrich_solution_now(conn, result.solution_id, service.get_problem(conn, 1), CODE)

    assert e.pattern == "hashmap"
    assert e.embed_skipped
    assert e.neighbors == []
    # the tags still landed - only the vector is missing
    assert conn.execute("SELECT COUNT(*) FROM enrichments").fetchone()[0] == 1


def test_enrich_solution_now_flags_off_pattern(tmp_path, monkeypatch):
    conn = setup_env(tmp_path, monkeypatch)
    off = ENRICHMENT.model_copy(update={"pattern": "prefix-sum", "intended_pattern": "dp-1d"})
    monkeypatch.setattr("coach.llm.parse", lambda prompt, output_format, **kw: off)
    monkeypatch.setattr("coach.embed.encode", fake_encode)
    result = service.log_solve(conn, 1, "clean", CODE)

    e = service.enrich_solution_now(conn, result.solution_id, service.get_problem(conn, 1), CODE)

    assert e.off_pattern is True
    assert e.intended_pattern == "dp-1d"
    assert conn.execute("SELECT intended_pattern FROM problems").fetchone()[0] == "dp-1d"


def test_enrich_solution_now_accepts_a_canonical_alternate_approach(tmp_path, monkeypatch):
    """The whole point of intended_secondary_patterns: a different but still
    canonical route is not off-pattern, and earns no forced re-solve."""
    conn = setup_env(tmp_path, monkeypatch)
    alternate = ENRICHMENT.model_copy(update={"pattern": "two-pointers"})
    monkeypatch.setattr("coach.llm.parse", lambda prompt, output_format, **kw: alternate)
    monkeypatch.setattr("coach.embed.encode", fake_encode)
    result = service.log_solve(conn, 1, "clean", CODE)

    e = service.enrich_solution_now(conn, result.solution_id, service.get_problem(conn, 1), CODE)

    assert e.off_pattern is False
    # the note still points at the approach that went unpractised
    assert e.also_solvable_with == ["hashmap"]
    assert e.intended_secondary_patterns == ["two-pointers"]
    assert enrich.off_pattern_problems(conn) == []


def test_enrich_solution_now_carries_both_signals_when_embedding_fails(tmp_path, monkeypatch):
    """The early return path must not drop the new fields."""
    conn = setup_env(tmp_path, monkeypatch)
    off = ENRICHMENT.model_copy(update={"pattern": "prefix-sum", "intended_pattern": "dp-1d"})
    monkeypatch.setattr("coach.llm.parse", lambda prompt, output_format, **kw: off)
    monkeypatch.setattr(
        "coach.embed.encode",
        lambda texts: (_ for _ in ()).throw(embed.EmbeddingsUnavailable("no model")),
    )
    result = service.log_solve(conn, 1, "clean", CODE)

    e = service.enrich_solution_now(conn, result.solution_id, service.get_problem(conn, 1), CODE)

    assert e.embed_skipped
    assert e.off_pattern is True
    assert e.also_solvable_with == ["dp-1d", "two-pointers"]
    assert e.intended_secondary_patterns == ["two-pointers"]


def test_pattern_counts_credits_every_pattern_a_problem_was_practiced_with(tmp_path, monkeypatch):
    conn = setup_env(tmp_path, monkeypatch)
    monkeypatch.setattr("coach.embed.encode", fake_encode)

    # one problem solved three times: two approaches, the second one repeated
    for pattern in ("prefix-sum", "hashmap", "hashmap"):
        e = ENRICHMENT.model_copy(update={"pattern": pattern})
        monkeypatch.setattr("coach.llm.parse", lambda prompt, output_format, _e=e, **kw: _e)
        r = service.log_solve(conn, 1, "clean", CODE)
        service.enrich_solution_now(conn, r.solution_id, service.get_problem(conn, 1), CODE)

    # both approaches counted, and the repeated one still counts once
    assert service.pattern_counts(conn) == [
        {"pattern": "hashmap", "solved": 1},
        {"pattern": "prefix-sum", "solved": 1},
    ]


def test_pattern_counts_includes_a_solutions_secondary_patterns(tmp_path, monkeypatch):
    conn = setup_env(tmp_path, monkeypatch)
    monkeypatch.setattr("coach.embed.encode", fake_encode)
    e = ENRICHMENT.model_copy(update={"secondary_patterns": ["two-pointers"]})
    monkeypatch.setattr("coach.llm.parse", lambda prompt, output_format, **kw: e)
    r = service.log_solve(conn, 1, "clean", CODE)
    service.enrich_solution_now(conn, r.solution_id, service.get_problem(conn, 1), CODE)

    assert service.pattern_counts(conn) == [
        {"pattern": "hashmap", "solved": 1},
        {"pattern": "two-pointers", "solved": 1},
    ]


def log_and_enrich(conn, monkeypatch, outcome, pattern="hashmap"):
    e = ENRICHMENT.model_copy(update={"pattern": pattern, "intended_pattern": pattern})
    monkeypatch.setattr("coach.llm.parse", lambda prompt, output_format, _e=e, **kw: _e)
    monkeypatch.setattr("coach.embed.encode", fake_encode)
    r = service.log_solve(conn, 1, outcome, CODE)
    return service.enrich_solution_now(conn, r.solution_id, service.get_problem(conn, 1), CODE)


def test_pattern_standing_is_none_without_a_pattern(tmp_path, monkeypatch):
    """No pattern means enrichment was skipped - there is nothing to stand on."""
    conn = setup_env(tmp_path, monkeypatch)

    assert service.pattern_standing(conn, None) is None
    assert service.pattern_standing(conn, "never-solved") is None


def test_pattern_standing_withholds_a_verdict_on_a_first_attempt(tmp_path, monkeypatch):
    conn = setup_env(tmp_path, monkeypatch)
    log_and_enrich(conn, monkeypatch, "failed")

    assert service.pattern_standing(conn, "hashmap") == service.PatternStanding(
        pattern="hashmap", attempts=1, struggle_rate=1.0, score=1.0, weak=False, enough_data=False
    )


def test_pattern_standing_calls_a_pattern_weak_once_there_is_data(tmp_path, monkeypatch):
    conn = setup_env(tmp_path, monkeypatch)
    for _ in range(5):
        log_and_enrich(conn, monkeypatch, "failed")

    assert service.pattern_standing(conn, "hashmap") == service.PatternStanding(
        pattern="hashmap", attempts=5, struggle_rate=1.0, score=1.0, weak=True, enough_data=True
    )


def test_pattern_standing_stays_clear_of_weak_on_clean_solves(tmp_path, monkeypatch):
    conn = setup_env(tmp_path, monkeypatch)
    for _ in range(5):
        log_and_enrich(conn, monkeypatch, "clean")

    assert service.pattern_standing(conn, "hashmap") == service.PatternStanding(
        pattern="hashmap", attempts=5, struggle_rate=0.0, score=5.0, weak=False, enough_data=True
    )


def test_pattern_standing_separates_struggling_from_failing(tmp_path, monkeypatch):
    """Same 100% struggle rate as the weak case above, a very different score."""
    conn = setup_env(tmp_path, monkeypatch)
    for _ in range(5):
        log_and_enrich(conn, monkeypatch, "struggled")

    standing = service.pattern_standing(conn, "hashmap")
    assert standing.struggle_rate == 1.0
    assert standing.score == pytest.approx(3.0)
    assert standing.weak is False


def test_a_stored_review_pulls_the_pattern_score_down(tmp_path, monkeypatch):
    """A solve can feel clean and still carry a bug - that is what the review adds."""
    conn = setup_env(tmp_path, monkeypatch)
    for _ in range(4):
        log_and_enrich(conn, monkeypatch, "clean")
    result = service.log_solve(conn, 1, "clean", CODE)
    service.enrich_solution_now(conn, result.solution_id, service.get_problem(conn, 1), CODE)
    assert service.pattern_standing(conn, "hashmap").score == 5.0

    monkeypatch.setattr("coach.llm.parse", lambda prompt, output_format, **kw: FEEDBACK)
    service.review_solution_now(
        conn, result.solution_id, service.get_problem(conn, 1), CODE, refresh=True
    )

    # 0.7*5 + 0.3*1 = 3.8 for that solve, folded in at alpha 0.2: 0.8*5 + 0.2*3.8
    assert service.pattern_standing(conn, "hashmap").score == pytest.approx(4.76)


def test_stats_summary_counts_distinct_problems_and_curriculum(tmp_path, monkeypatch):
    conn = setup_env(
        tmp_path,
        monkeypatch,
        problems=[
            {
                "number": 1,
                "slug": "two-sum",
                "title": "Two Sum",
                "difficulty": "Easy",
                "official_tags": "[]",
                "paid_only": 0,
            },
            {
                "number": 15,
                "slug": "3sum",
                "title": "3Sum",
                "difficulty": "Medium",
                "official_tags": "[]",
                "paid_only": 0,
            },
        ],
    )
    conn.execute("UPDATE problems SET in_blind75 = 1")
    today = date(2026, 9, 1)
    service.log_solve(conn, 1, "clean", CODE, today=today)
    service.log_solve(conn, 1, "struggled", CODE, today=today)
    service.log_solve(conn, 15, "clean", CODE, today=today)

    s = service.stats_summary(conn, today)

    assert s == {
        "catalog": 2,
        "solved": 2,
        "attempts": 3,
        "last_7_days": 3,
        "due_today": 0,
        "outcomes": [{"outcome": "clean", "count": 2}, {"outcome": "struggled", "count": 1}],
        "patterns": [],
        "off_pattern": [],
        "curriculum": {"blind75": {"done": 2, "total": 2}, "neetcode150": {"done": 0, "total": 0}},
    }


def test_solution_history_returns_every_solve_newest_first(tmp_path, monkeypatch):
    conn = setup_env(tmp_path, monkeypatch)
    service.log_solve(conn, 1, "failed", "first attempt\n")
    log_and_enrich(conn, monkeypatch, "clean")

    history = service.solution_history(conn, 1)

    assert history["title"] == "Two Sum"
    assert [s["outcome"] for s in history["solves"]] == ["clean", "failed"]
    assert history["solves"][1]["code"] == "first attempt"
    assert history["solves"][0]["pattern"] == "hashmap"
    assert history["solves"][1]["pattern"] is None  # logged before enrichment ran


def test_solution_history_notes_the_canonical_approaches_not_used(tmp_path, monkeypatch):
    """Computed per load rather than frozen, so widening the problem's canonical
    set later widens the note on solves that were stored before it."""
    conn = setup_env(tmp_path, monkeypatch)
    service.log_solve(conn, 1, "failed", "first attempt\n")  # never enriched
    log_and_enrich(conn, monkeypatch, "clean")

    solves = service.solution_history(conn, 1)["solves"]
    assert solves[0]["also_solvable_with"] == ["two-pointers"]
    assert solves[1]["also_solvable_with"] == []  # no pattern to compare against

    enrich.save_intended(conn, 1, "hashmap", ["two-pointers", "binary-search"])
    conn.commit()
    history = service.solution_history(conn, 1)
    assert history["solves"][0]["also_solvable_with"] == ["two-pointers", "binary-search"]
    assert history["intended_secondary_patterns"] == ["two-pointers", "binary-search"]


def test_also_solvable_with_is_empty_for_an_unenriched_solve(tmp_path, monkeypatch):
    conn = setup_env(tmp_path, monkeypatch)
    result = service.log_solve(conn, 1, "failed", CODE)

    problem = service.get_problem(conn, 1)
    assert service.also_solvable_with(conn, result.solution_id, problem) == []


def test_solution_history_rejects_an_unknown_problem(tmp_path, monkeypatch):
    conn = setup_env(tmp_path, monkeypatch)

    with pytest.raises(service.ProblemNotFound):
        service.solution_history(conn, 99999)
    assert service.solution_history(conn, 1)["solves"] == []


def test_solved_problems_aggregates_one_row_per_problem(tmp_path, monkeypatch):
    conn = setup_env(tmp_path, monkeypatch)
    log_and_enrich(conn, monkeypatch, "struggled")
    log_and_enrich(conn, monkeypatch, "clean")

    rows = service.solved_problems(conn)

    assert len(rows) == 1
    assert rows[0]["number"] == 1
    assert rows[0]["solves"] == 2
    assert rows[0]["last_outcome"] == "clean"
    assert rows[0]["pattern"] == "hashmap"


def test_coach_db_env_var_redirects_the_database(tmp_path, monkeypatch):
    """COACH_DB is the documented way to run against a scratch database."""
    monkeypatch.setenv("COACH_DB", str(tmp_path / "scratch.db"))
    # config.load_env() runs on import; keep it from re-seeding a real key from .env
    monkeypatch.setenv("ANTHROPIC_API_KEY", "not-a-real-key")
    try:
        importlib.reload(config)
        assert config.DB_PATH == tmp_path / "scratch.db"
    finally:
        monkeypatch.delenv("COACH_DB")
        importlib.reload(config)
    assert config.DB_PATH == config.DATA_DIR / "coach.db"
