import importlib
from datetime import date, timedelta

import numpy as np
import pytest
from conftest import CODE, TWO_SUM, seed_db

from coach import config, embed, enrich, mastery, review, service
from coach.weekly import analyze as weekly_analyze
from coach.weekly import collect as weekly_collect

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


def test_log_solve_stores_attempt_solution_and_schedule(tmp_path, monkeypatch):
    conn = seed_db(tmp_path, monkeypatch)

    result = service.log_solve(conn, 1, "struggled", CODE, minutes=25, today=date(2026, 9, 1))

    assert result.title == "Two Sum"
    assert result.next_due == date(2026, 9, 8)
    assert conn.execute("SELECT minutes FROM attempts").fetchone()["minutes"] == 25
    assert conn.execute("SELECT code FROM solutions").fetchone()["code"].startswith("class Solution")


def test_log_solve_rejects_unknown_problem_and_empty_code(tmp_path, monkeypatch):
    conn = seed_db(tmp_path, monkeypatch)

    with pytest.raises(service.ProblemNotFound):
        service.log_solve(conn, 99999, "clean", CODE)
    with pytest.raises(service.EmptySolution):
        service.log_solve(conn, 1, "clean", "   \n ")
    assert conn.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0


def test_second_log_advances_the_schedule(tmp_path, monkeypatch):
    """log_solve reads the stored review state before rescheduling, so a second
    clean solve steps up to the second interval rather than restarting at the first."""
    conn = seed_db(tmp_path, monkeypatch)
    service.log_solve(conn, 1, "clean", CODE, today=date(2026, 9, 1))

    result = service.log_solve(conn, 1, "clean", CODE, today=date(2026, 9, 8))

    state = conn.execute("SELECT reps, interval_days FROM review_state").fetchone()
    assert (state["reps"], state["interval_days"]) == (2, 14.0)
    assert result.next_due == date(2026, 9, 22)


def test_enrich_solution_now_reports_llm_degradation(tmp_path, monkeypatch):
    conn = seed_db(tmp_path, monkeypatch)
    result = service.log_solve(conn, 1, "clean", CODE)
    problem = service.get_problem(conn, 1)

    e = service.enrich_solution_now(conn, result.solution_id, problem, CODE)

    assert e.pattern is None
    assert "ANTHROPIC_API_KEY" in e.skipped
    assert conn.execute("SELECT COUNT(*) FROM enrichments").fetchone()[0] == 0


def test_enrich_solution_now_reports_embedding_degradation(tmp_path, monkeypatch):
    conn = seed_db(tmp_path, monkeypatch)
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
    conn = seed_db(tmp_path, monkeypatch)
    off = ENRICHMENT.model_copy(update={"pattern": "prefix-sum", "intended_pattern": "dp-1d"})
    monkeypatch.setattr("coach.llm.parse", lambda prompt, output_format, **kw: off)
    monkeypatch.setattr("coach.embed.encode", fake_encode)
    result = service.log_solve(conn, 1, "clean", CODE)

    e = service.enrich_solution_now(conn, result.solution_id, service.get_problem(conn, 1), CODE)

    assert e.off_pattern is True
    assert e.intended_pattern == "dp-1d"
    # both halves of the problem's canonical set are stored, not just the central one
    assert service.problem_canonical(service.get_problem(conn, 1)) == ("dp-1d", ["two-pointers"])


def test_enrich_solution_now_accepts_a_canonical_alternate_approach(tmp_path, monkeypatch):
    """The whole point of intended_secondary_patterns: a different but still
    canonical route is not off-pattern, and earns no forced re-solve."""
    conn = seed_db(tmp_path, monkeypatch)
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
    conn = seed_db(tmp_path, monkeypatch)
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


def enrich_against_stored_canonical(conn, monkeypatch, **answer):
    """Enrich a new Two Sum solve whose stored canonical set is hashmap + two-pointers,
    with a model answer overridden by `answer`."""
    enrich.save_intended(conn, 1, "hashmap", ["two-pointers"])
    conn.commit()
    e = ENRICHMENT.model_copy(update=answer)
    monkeypatch.setattr("coach.llm.parse", lambda prompt, output_format, **kw: e)
    monkeypatch.setattr("coach.embed.encode", fake_encode)
    result = service.log_solve(conn, 1, "clean", CODE)
    return service.enrich_solution_now(conn, result.solution_id, service.get_problem(conn, 1), CODE)


def test_enrich_solution_now_judges_against_the_stored_set_not_the_latest_answer(
    tmp_path, monkeypatch
):
    """save_intended accumulates alternates, but the response used to be judged against
    the model's latest answer alone - so the moment the model forgot an approach it had
    accepted before, a solve the planner had cleared was reported off-pattern."""
    conn = seed_db(tmp_path, monkeypatch)

    e = enrich_against_stored_canonical(
        conn, monkeypatch, pattern="two-pointers", intended_secondary_patterns=[]
    )

    assert e.off_pattern is False
    assert e.intended_secondary_patterns == ["two-pointers"]
    assert e.also_solvable_with == ["hashmap"]
    # the response, the stored problem and the planner all read one set
    assert (e.intended_pattern, e.intended_secondary_patterns) == service.problem_canonical(
        service.get_problem(conn, 1)
    )
    assert weekly_analyze.analyze(conn, date.today())["off_pattern"] == []


def test_enrich_solution_now_keeps_a_demoted_central_pattern_canonical(tmp_path, monkeypatch):
    conn = seed_db(tmp_path, monkeypatch)

    e = enrich_against_stored_canonical(
        conn,
        monkeypatch,
        pattern="hashmap",
        intended_pattern="two-pointers",
        intended_secondary_patterns=[],
    )

    assert e.off_pattern is False
    assert e.intended_pattern == "two-pointers"
    assert e.intended_secondary_patterns == ["hashmap"]
    assert e.also_solvable_with == ["two-pointers"]


def test_enrich_solution_now_lists_a_repeated_alternate_once(tmp_path, monkeypatch):
    conn = seed_db(tmp_path, monkeypatch)

    e = enrich_against_stored_canonical(
        conn, monkeypatch, intended_secondary_patterns=["two-pointers", "hashmap", "two-pointers"]
    )

    assert e.intended_secondary_patterns == ["two-pointers"]
    assert e.also_solvable_with == ["two-pointers"]


def test_pattern_counts_credits_every_pattern_a_problem_was_practiced_with(tmp_path, monkeypatch):
    conn = seed_db(tmp_path, monkeypatch)
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
    conn = seed_db(tmp_path, monkeypatch)
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


def test_pattern_table_joins_mastery_to_every_credited_pattern(tmp_path, monkeypatch):
    """Practice is measured on the pattern a solve led with. A pattern credited only
    as a secondary has coverage but no practice - None, not a zero that would read
    as practiced-and-failed."""
    conn = seed_db(tmp_path, monkeypatch)
    e = ENRICHMENT.model_copy(update={"secondary_patterns": ["two-pointers"]})
    monkeypatch.setattr("coach.llm.parse", lambda prompt, output_format, **kw: e)
    monkeypatch.setattr("coach.embed.encode", fake_encode)
    result = service.log_solve(conn, 1, "struggled", CODE)
    service.enrich_solution_now(conn, result.solution_id, service.get_problem(conn, 1), CODE)

    table = {row["pattern"]: row for row in service.pattern_table(conn)}

    assert table["hashmap"] == {
        "pattern": "hashmap", "solved": 1, "score": 3.0, "attempts": 1, "rough": 1,
    }
    assert table["two-pointers"] == {
        "pattern": "two-pointers", "solved": 1, "score": None, "attempts": None, "rough": None,
    }


def test_pattern_standing_is_none_without_a_pattern(tmp_path, monkeypatch):
    """No pattern means enrichment was skipped - there is nothing to stand on."""
    conn = seed_db(tmp_path, monkeypatch)

    assert service.pattern_standing(conn, None) is None
    assert service.pattern_standing(conn, "never-solved") is None


def test_pattern_standing_withholds_a_verdict_on_a_first_attempt(tmp_path, monkeypatch):
    conn = seed_db(tmp_path, monkeypatch)
    log_and_enrich(conn, monkeypatch, "failed")

    assert service.pattern_standing(conn, "hashmap") == service.PatternStanding(
        pattern="hashmap", attempts=1, struggle_rate=1.0, score=1.0, weak=False, enough_data=False
    )


def test_pattern_standing_calls_a_pattern_weak_once_there_is_data(tmp_path, monkeypatch):
    conn = seed_db(tmp_path, monkeypatch)
    for _ in range(5):
        log_and_enrich(conn, monkeypatch, "failed")

    assert service.pattern_standing(conn, "hashmap") == service.PatternStanding(
        pattern="hashmap", attempts=5, struggle_rate=1.0, score=1.0, weak=True, enough_data=True
    )


def test_pattern_standing_stays_clear_of_weak_on_clean_solves(tmp_path, monkeypatch):
    conn = seed_db(tmp_path, monkeypatch)
    for _ in range(5):
        log_and_enrich(conn, monkeypatch, "clean")

    assert service.pattern_standing(conn, "hashmap") == service.PatternStanding(
        pattern="hashmap", attempts=5, struggle_rate=0.0, score=5.0, weak=False, enough_data=True
    )


def test_pattern_standing_separates_struggling_from_failing(tmp_path, monkeypatch):
    """Same 100% struggle rate as the weak case above, a very different score."""
    conn = seed_db(tmp_path, monkeypatch)
    for _ in range(5):
        log_and_enrich(conn, monkeypatch, "struggled")

    standing = service.pattern_standing(conn, "hashmap")
    assert standing.struggle_rate == 1.0
    assert standing.score == pytest.approx(3.0)
    assert standing.weak is False


def test_a_stored_review_pulls_the_pattern_score_down(tmp_path, monkeypatch):
    """A solve can feel clean and still carry a bug - that is what the review adds."""
    conn = seed_db(tmp_path, monkeypatch)
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


def test_saved_evidence_is_read_without_any_rebuild(tmp_path, monkeypatch):
    """Mastery follows what is saved, whoever saved it. Tagged and reviewed through the
    persistence functions alone - no service orchestration after the commit - every
    reader still sees the review, so no writer has to remember a refresh."""
    conn = seed_db(tmp_path, monkeypatch)
    today = date.today()
    for _ in range(5):
        result = service.log_solve(conn, 1, "clean", CODE, today=today)
        enrich.save(conn, result.solution_id, ENRICHMENT)
    review.save(conn, result.solution_id, FEEDBACK)
    conn.commit()

    reviewed = pytest.approx(4.76)  # four clean solves, then 0.7*5 + 0.3*1 folded in
    assert service.pattern_table(conn)[0]["score"] == reviewed
    assert service.pattern_standing(conn, "hashmap", today).score == reviewed
    plan = service.daily_plan(conn, today, config.DAILY_TARGET)
    assert plan.analysis["patterns"][0]["score"] == reviewed
    assert service.weekly_review(conn, today).patterns[0].score == reviewed


def test_mastery_readers_write_nothing_and_call_no_model(tmp_path, monkeypatch):
    """Every page load reads mastery, so reading it must stay free."""
    conn = seed_db(tmp_path, monkeypatch)
    for _ in range(5):
        log_and_enrich(conn, monkeypatch, "failed")
    monkeypatch.setattr(
        "coach.llm.parse", lambda *args, **kw: pytest.fail("a mastery reader called the model")
    )
    today = date.today()
    before = conn.total_changes

    service.pattern_table(conn)
    service.pattern_standing(conn, "hashmap", today)
    service.daily_plan(conn, today, config.DAILY_TARGET)
    service.weekly_review(conn, today)

    assert conn.total_changes == before


def test_stats_summary_counts_distinct_problems_and_curriculum(tmp_path, monkeypatch):
    conn = seed_db(
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
        "curriculum": {"blind75": {"done": 2, "total": 2}, "neetcode150": {"done": 0, "total": 0}},
    }


def test_last_7_days_covers_the_same_window_the_weekly_report_collects(tmp_path, monkeypatch):
    """One definition of "the last week", not two.

    `date >= today - 7` counted today plus the seven days before it - eight - so
    the home page reported 8 where the weekly report reported 7 for the same solves.
    """
    conn = seed_db(tmp_path, monkeypatch)
    today = date(2026, 9, 7)
    for days_ago in range(10):
        service.log_solve(conn, 1, "clean", CODE, today=today - timedelta(days=days_ago))

    counted = service.stats_summary(conn, today)["last_7_days"]
    week = weekly_collect.collect(conn, today)

    assert counted == weekly_collect.WINDOW_DAYS == 7
    assert counted == len(week["attempts"])
    # the eighth day back is outside the window on both sides
    assert week["start"] == today - timedelta(days=6)


def test_solution_history_returns_every_solve_newest_first(tmp_path, monkeypatch):
    conn = seed_db(tmp_path, monkeypatch)
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
    conn = seed_db(tmp_path, monkeypatch)
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


def test_solution_history_rejects_an_unknown_problem(tmp_path, monkeypatch):
    conn = seed_db(tmp_path, monkeypatch)

    with pytest.raises(service.ProblemNotFound):
        service.solution_history(conn, 99999)
    assert service.solution_history(conn, 1)["solves"] == []


def test_solved_problems_aggregates_one_row_per_problem(tmp_path, monkeypatch):
    conn = seed_db(tmp_path, monkeypatch)
    log_and_enrich(conn, monkeypatch, "struggled")
    log_and_enrich(conn, monkeypatch, "clean")

    rows = service.solved_problems(conn)

    assert len(rows) == 1
    assert rows[0]["number"] == 1
    assert rows[0]["solves"] == 2
    assert rows[0]["last_outcome"] == "clean"
    assert rows[0]["pattern"] == "hashmap"


THREE_SUM = {
    "number": 15,
    "slug": "3sum",
    "title": "3Sum",
    "difficulty": "Medium",
    "official_tags": '["array", "two-pointers"]',
    "paid_only": 0,
}


def listed(rows):
    return [r["number"] for r in rows]


def test_solved_problems_puts_the_last_logged_first_on_the_same_day(tmp_path, monkeypatch):
    """created_at is a date, so same-day solves tie on it - and the problem number
    used to break the tie, listing #1 above a #15 logged after it."""
    conn = seed_db(tmp_path, monkeypatch, TWO_SUM + [THREE_SUM])
    day = date(2026, 9, 7)
    service.log_solve(conn, 1, "clean", CODE, today=day)
    service.log_solve(conn, 15, "clean", CODE, today=day)
    assert listed(service.solved_problems(conn)) == [15, 1]

    service.log_solve(conn, 1, "clean", CODE, today=day)
    assert listed(service.solved_problems(conn)) == [1, 15]


def test_solutions_listing_defaults_to_the_most_recent(tmp_path, monkeypatch):
    conn = seed_db(tmp_path, monkeypatch, TWO_SUM + [THREE_SUM])
    service.log_solve(conn, 1, "failed", CODE)
    service.log_solve(conn, 1, "clean", CODE)
    service.log_solve(conn, 15, "clean", CODE)

    listing = service.solutions_listing(conn, recent=1)

    assert listed(listing["problems"]) == [15]
    assert listing["query"] == ""
    # The totals count everything, not just the rows the cap let through.
    assert (listing["total_problems"], listing["total_solves"]) == (2, 3)


def test_solutions_listing_matches_number_prefix_and_title(tmp_path, monkeypatch):
    conn = seed_db(tmp_path, monkeypatch, TWO_SUM + [THREE_SUM])
    service.log_solve(conn, 1, "clean", CODE)
    service.log_solve(conn, 15, "clean", CODE)

    def search(query):
        return listed(service.solutions_listing(conn, query, recent=1)["problems"])

    assert search("1") == [15, 1]  # number prefix - and not capped by recent=1
    assert search("15") == [15]
    assert search("5") == []  # a prefix, not "contains": 15 does not start with 5
    assert search("SUM") == [15, 1]  # title, case-insensitive
    assert search(" two ") == [1]
    assert search("zzz") == []
    assert search("  ") == [15]  # blank is no search - the default view


WEEK_TODAY = date(2026, 9, 7)


def scored_attempt(conn, day, outcome, pattern="hashmap", number=1):
    """One enriched solve, scored - the history a mastery number folds over."""
    attempt_id = conn.execute(
        "INSERT INTO attempts (problem_number, date, outcome) VALUES (?, ?, ?)",
        (number, day.isoformat(), outcome),
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
    conn.commit()
    return solution_id


def test_weekly_review_collects_the_window_and_the_patterns_in_it(tmp_path, monkeypatch):
    conn = seed_db(tmp_path, monkeypatch)
    scored_attempt(conn, WEEK_TODAY - timedelta(days=2), "clean")
    scored_attempt(conn, WEEK_TODAY - timedelta(days=20), "failed", pattern="dp-1d")

    review = service.weekly_review(conn, WEEK_TODAY)

    assert review.start == WEEK_TODAY - timedelta(days=6)
    assert review.end == WEEK_TODAY
    assert len(review.attempts) == 1
    assert review.distinct_problems == 1
    # dp-1d has all-time history but was not practiced in the window.
    assert [p.pattern for p in review.patterns] == ["hashmap"]


def test_weekly_review_counts_an_untagged_solve_without_inventing_a_pattern(tmp_path, monkeypatch):
    """Enrichment can be skipped (no API key), and the solve is still a solve."""
    conn = seed_db(tmp_path, monkeypatch)
    scored_attempt(conn, WEEK_TODAY, "clean", pattern=None)

    review = service.weekly_review(conn, WEEK_TODAY)

    assert len(review.attempts) == 1
    assert review.attempts[0]["pattern"] is None
    assert review.patterns == []


def test_weekly_review_says_too_early_below_the_attempt_floor(tmp_path, monkeypatch):
    conn = seed_db(tmp_path, monkeypatch)
    for day in range(4):
        scored_attempt(conn, WEEK_TODAY - timedelta(days=day), "failed")

    p = service.weekly_review(conn, WEEK_TODAY).patterns[0]

    assert p.attempts_total == 4 < mastery.WEAK_MIN_ATTEMPTS
    assert p.standing == "too-early"


def test_weekly_review_standing_tracks_the_analysis_verdict(tmp_path, monkeypatch):
    """weak is only ever membership in analysis["weak_patterns"] - never a
    threshold re-derived here, which is how the two definitions drift apart."""
    conn = seed_db(tmp_path, monkeypatch)
    for day in range(5):
        scored_attempt(conn, WEEK_TODAY - timedelta(days=day), "failed")

    review = service.weekly_review(conn, WEEK_TODAY)
    analysis = weekly_analyze.analyze(conn, WEEK_TODAY)

    assert analysis["weak_patterns"] == ["hashmap"]
    assert review.patterns[0].standing == "weak"

    # Five struggled-but-solved attempts are the same struggle rate and not weak.
    conn.execute("UPDATE attempts SET outcome = 'struggled'")
    assert service.weekly_review(conn, WEEK_TODAY).patterns[0].standing == "on-track"


def test_weekly_review_measures_the_week_against_where_it_started(tmp_path, monkeypatch):
    conn = seed_db(tmp_path, monkeypatch)
    for day in range(12, 7, -1):  # five failures, all before the window
        scored_attempt(conn, WEEK_TODAY - timedelta(days=day), "failed")
    scored_attempt(conn, WEEK_TODAY, "clean")

    p = service.weekly_review(conn, WEEK_TODAY).patterns[0]

    assert p.attempts_week == 1
    assert p.attempts_total == 6
    assert p.score_before == pytest.approx(1.0)  # five failures
    assert p.score == pytest.approx(1.8)  # one clean solve, EMA alpha 0.2
    assert p.delta == pytest.approx(0.8)


def test_weekly_review_has_no_delta_for_a_pattern_first_seen_this_week(tmp_path, monkeypatch):
    conn = seed_db(tmp_path, monkeypatch)
    scored_attempt(conn, WEEK_TODAY, "clean")

    p = service.weekly_review(conn, WEEK_TODAY).patterns[0]

    assert p.score_before is None
    assert p.delta is None


def test_weekly_review_orders_the_worst_patterns_first(tmp_path, monkeypatch):
    conn = seed_db(tmp_path, monkeypatch)
    for day in range(5):
        scored_attempt(conn, WEEK_TODAY - timedelta(days=day), "failed", pattern="dp-1d")
        scored_attempt(conn, WEEK_TODAY - timedelta(days=day), "clean", pattern="hashmap")
    scored_attempt(conn, WEEK_TODAY, "clean", pattern="graphs")

    review = service.weekly_review(conn, WEEK_TODAY)

    assert [(p.pattern, p.standing) for p in review.patterns] == [
        ("dp-1d", "weak"),
        ("hashmap", "on-track"),
        ("graphs", "too-early"),
    ]


def test_weekly_review_loads_history_once(tmp_path, monkeypatch):
    """Current mastery and the week's baseline come from one read, not two replays."""
    conn = seed_db(tmp_path, monkeypatch)
    scored_attempt(conn, WEEK_TODAY - timedelta(days=10), "failed")
    scored_attempt(conn, WEEK_TODAY, "clean")
    loads = []
    real = mastery.load_history
    monkeypatch.setattr(mastery, "load_history", lambda conn: loads.append(conn) or real(conn))

    p = service.weekly_review(conn, WEEK_TODAY).patterns[0]

    assert len(loads) == 1
    assert (p.score_before, p.score) == (pytest.approx(1.0), pytest.approx(1.8))


def test_daily_plan_only_counts_reviews_due_today(tmp_path, monkeypatch):
    conn = seed_db(
        tmp_path,
        monkeypatch,
        problems=[
            {"number": 1, "slug": "two-sum", "title": "Two Sum", "difficulty": "Easy",
             "official_tags": '["array"]', "paid_only": 0},
            {"number": 2, "slug": "coin-change", "title": "Coin Change", "difficulty": "Medium",
             "official_tags": '["array"]', "paid_only": 0},
        ],
    )
    today = date(2026, 9, 7)
    for number, due in ((1, today), (2, today + timedelta(days=3))):
        conn.execute(
            """
            INSERT INTO review_state (problem_number, ease, interval_days, next_due, reps, lapses)
            VALUES (?, 2.5, 7.0, ?, 1, 0)
            """,
            (number, due.isoformat()),
        )

    items = service.daily_plan(conn, today, target=4).items

    assert [i.number for i in items] == [1]
    assert items[0].reason == f"review due {today.isoformat()}"


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
