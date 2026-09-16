import importlib
from datetime import date, timedelta

import httpx
import numpy as np
import pytest
from conftest import CODE, TWO_SUM, seed_db, tag_solution

from coach import (
    config,
    corrections,
    db,
    embed,
    enrich,
    history,
    llm,
    mastery,
    review,
    service,
)
from coach.weekly import analyze as weekly_analyze
from coach.weekly import collect as weekly_collect

ENRICHMENT = enrich.Enrichment(
    main_patterns=["hashmap"],
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
    """log_solve reschedules from every attempt logged before, so a clean solve a
    week later steps up to the second interval rather than restarting at the first."""
    conn = seed_db(tmp_path, monkeypatch)
    first = service.log_solve(conn, 1, "clean", CODE, today=date(2026, 9, 1))

    result = service.log_solve(conn, 1, "clean", CODE, today=date(2026, 9, 8))

    state = conn.execute("SELECT reps, interval_days FROM review_state").fetchone()
    assert (state["reps"], state["interval_days"]) == (2, 14.0)
    assert result.next_due == date(2026, 9, 22)
    assert (first.counted_as_review, result.counted_as_review) == (True, True)


def test_relogging_a_problem_the_same_day_keeps_its_review_date(tmp_path, monkeypatch):
    """Three solves of one problem in one sitting are one review. Each used to count,
    stepping the schedule 7 -> 14 -> 39 days as if a month of remembering had been shown."""
    conn = seed_db(tmp_path, monkeypatch)

    results = [service.log_solve(conn, 1, "clean", CODE, today=date(2026, 9, 1)) for _ in range(3)]

    assert [r.next_due for r in results] == [date(2026, 9, 8)] * 3
    assert [r.counted_as_review for r in results] == [True, False, False]
    state = conn.execute("SELECT reps, interval_days FROM review_state").fetchone()
    assert (state["reps"], state["interval_days"]) == (1, 7.0)
    # every attempt is still kept - only the schedule counts the day once
    assert conn.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 3


def test_a_failed_retry_the_same_day_still_brings_the_review_forward(tmp_path, monkeypatch):
    conn = seed_db(tmp_path, monkeypatch)
    service.log_solve(conn, 1, "clean", CODE, today=date(2026, 9, 1))

    result = service.log_solve(conn, 1, "failed", CODE, today=date(2026, 9, 1))

    assert result.next_due == date(2026, 9, 4)


def stored_schedule(conn, number=1) -> tuple[date, int, int]:
    """(next_due, reps, lapses) as review_state holds them."""
    row = conn.execute(
        "SELECT next_due, reps, lapses FROM review_state WHERE problem_number = ?", (number,)
    ).fetchone()
    return date.fromisoformat(row["next_due"]), row["reps"], row["lapses"]


def test_a_clean_solve_before_the_review_is_due_keeps_its_date(tmp_path, monkeypatch):
    """Solving again two days on shows nothing about remembering it a week out, so the
    review stays on 09-08 - it used to step to a 14-day interval from 09-03."""
    conn = seed_db(tmp_path, monkeypatch)

    results = [
        service.log_solve(conn, 1, "clean", CODE, today=day)
        for day in (date(2026, 9, 1), date(2026, 9, 3))
    ]

    assert [(r.next_due, r.counted_as_review) for r in results] == [
        (date(2026, 9, 8), True),
        (date(2026, 9, 8), False),
    ]
    assert stored_schedule(conn) == (date(2026, 9, 8), 1, 0)


def test_a_failed_solve_before_the_review_is_due_resets_it(tmp_path, monkeypatch):
    conn = seed_db(tmp_path, monkeypatch)
    service.log_solve(conn, 1, "clean", CODE, today=date(2026, 9, 1))

    result = service.log_solve(conn, 1, "failed", CODE, today=date(2026, 9, 3))

    assert result.counted_as_review
    assert stored_schedule(conn) == (date(2026, 9, 6), 0, 1)


def test_a_stored_bug_review_lapses_the_attempt_it_judges(tmp_path, monkeypatch):
    """The solve felt clean, but its review reported a bug: the schedule reads that attempt
    as a lapse. log_solve never tags, so this also shows scheduling needs no enrichment."""
    conn = seed_db(tmp_path, monkeypatch)
    result = service.log_solve(conn, 1, "clean", CODE, today=date(2026, 9, 1))
    review.save(conn, result.solution_id, FEEDBACK)

    service.rebuild_review_states(conn)

    assert stored_schedule(conn) == (date(2026, 9, 4), 0, 1)


def test_logging_after_a_bug_review_replays_through_it(tmp_path, monkeypatch):
    """The next solve reschedules from the whole history, so it cannot forget the finding:
    a lapse on 09-01, then a first interval from 09-08 - not 09-08's second interval."""
    conn = seed_db(tmp_path, monkeypatch)
    first = service.log_solve(conn, 1, "clean", CODE, today=date(2026, 9, 1))
    review.save(conn, first.solution_id, FEEDBACK)

    result = service.log_solve(conn, 1, "clean", CODE, today=date(2026, 9, 8))

    assert result.next_due == date(2026, 9, 15)
    assert stored_schedule(conn) == (date(2026, 9, 15), 1, 1)


def test_a_clean_retry_the_same_day_does_not_clear_a_reported_bug(tmp_path, monkeypatch):
    conn = seed_db(tmp_path, monkeypatch)
    first = service.log_solve(conn, 1, "clean", CODE, today=date(2026, 9, 1))
    review.save(conn, first.solution_id, FEEDBACK)

    result = service.log_solve(conn, 1, "clean", CODE, today=date(2026, 9, 1))

    assert result.next_due == date(2026, 9, 4)


OPTIMAL_REVIEW = FEEDBACK.model_copy(update={"verdict": "optimal", "issues": []})
EDGE_REVIEW = FEEDBACK.model_copy(
    update={"issues": [review.Issue(category="edge-case", description="Empty input.")]}
)


def review_with(conn, monkeypatch, solution_id, answer, refresh=False):
    """Review a stored solve of problem 1 through the service, the model answering `answer`."""
    monkeypatch.setattr("coach.llm.parse", lambda prompt, output_format, **kw: answer)
    return service.review_solution_now(
        conn, solution_id, service.get_problem(conn, 1), CODE, refresh=refresh
    )


def test_a_review_reporting_a_bug_reschedules_its_problem(tmp_path, monkeypatch):
    """Saved on the real today, days after 09-01, yet the lapse lands three days after the
    attempt: a late review corrects the history instead of failing the problem today."""
    conn = seed_db(tmp_path, monkeypatch)
    logged = service.log_solve(conn, 1, "clean", CODE, today=date(2026, 9, 1))

    result = review_with(conn, monkeypatch, logged.solution_id, FEEDBACK)

    assert stored_schedule(conn) == (date(2026, 9, 4), 0, 1)
    assert result.effect == service.ReviewEffect(
        finding="bug",
        attempt_date=date(2026, 9, 1),
        latest_attempt_date=date(2026, 9, 1),
        next_due_before=date(2026, 9, 8),
        next_due=date(2026, 9, 4),
    )
    assert result.effect.rescheduled


def test_a_bug_in_an_older_attempt_replays_through_the_later_success(tmp_path, monkeypatch):
    """No failure is appended on the review date: 09-01 becomes a lapse, and the clean
    09-08 solve is a first interval after it - 09-15, where it was 09-22."""
    conn = seed_db(tmp_path, monkeypatch)
    older = service.log_solve(conn, 1, "clean", CODE, today=date(2026, 9, 1))
    service.log_solve(conn, 1, "clean", CODE, today=date(2026, 9, 8))

    result = review_with(conn, monkeypatch, older.solution_id, FEEDBACK)

    assert stored_schedule(conn) == (date(2026, 9, 15), 1, 1)
    assert (result.effect.attempt_date, result.effect.latest_attempt_date) == (
        date(2026, 9, 1),
        date(2026, 9, 8),
    )
    assert (result.effect.next_due_before, result.effect.next_due) == (
        date(2026, 9, 22),
        date(2026, 9, 15),
    )


def test_an_optimal_review_does_not_upgrade_a_failed_attempt(tmp_path, monkeypatch):
    conn = seed_db(tmp_path, monkeypatch)
    logged = service.log_solve(conn, 1, "failed", CODE, today=date(2026, 9, 1))

    result = review_with(conn, monkeypatch, logged.solution_id, OPTIMAL_REVIEW)

    assert stored_schedule(conn) == (date(2026, 9, 4), 0, 1)
    assert result.effect.finding is None
    assert not result.effect.rescheduled


def test_refreshing_a_review_that_drops_the_bug_restores_the_schedule(tmp_path, monkeypatch):
    conn = seed_db(tmp_path, monkeypatch)
    logged = service.log_solve(conn, 1, "clean", CODE, today=date(2026, 9, 1))
    review_with(conn, monkeypatch, logged.solution_id, FEEDBACK)

    review_with(conn, monkeypatch, logged.solution_id, OPTIMAL_REVIEW, refresh=True)

    assert stored_schedule(conn) == (date(2026, 9, 8), 1, 0)


def test_the_order_reviews_arrive_in_does_not_change_the_schedule(tmp_path, monkeypatch):
    """The same evidence gives the same schedule, and the one `coach init` would rebuild."""
    schedules = []
    for name, order in (("a", (0, 1)), ("b", (1, 0))):
        conn = seed_db(tmp_path / name, monkeypatch)
        solves = [
            service.log_solve(conn, 1, "clean", CODE, today=day).solution_id
            for day in (date(2026, 9, 1), date(2026, 9, 8))
        ]
        answers = (FEEDBACK, EDGE_REVIEW)
        for i in order:
            review_with(conn, monkeypatch, solves[i], answers[i])
        reviewed = conn.execute("SELECT * FROM review_state").fetchall()
        service.rebuild_review_states(conn)
        assert conn.execute("SELECT * FROM review_state").fetchall() == reviewed
        schedules.append([tuple(row) for row in reviewed])

    assert schedules[0] == schedules[1]
    # two lapses: 09-01 held at 1 by the bug, 09-08 at 2 by the edge case
    assert schedules[0][0][3:] == ("2026-09-11", 0, 2)


def test_a_review_that_lapses_an_earlier_day_can_make_a_later_solve_count(tmp_path, monkeypatch):
    """The 09-05 solve was early against a 09-08 review. Once a bug lapses 09-01 the review
    was due 09-04, so the replay counts 09-05 after all: a first interval, due 09-12."""
    conn = seed_db(tmp_path, monkeypatch)
    older = service.log_solve(conn, 1, "clean", CODE, today=date(2026, 9, 1))
    service.log_solve(conn, 1, "clean", CODE, today=date(2026, 9, 5))

    result = review_with(conn, monkeypatch, older.solution_id, FEEDBACK)

    assert stored_schedule(conn) == (date(2026, 9, 12), 1, 1)
    assert (result.effect.next_due_before, result.effect.next_due) == (
        date(2026, 9, 8),
        date(2026, 9, 12),
    )


def test_asking_again_for_a_stored_review_writes_nothing(tmp_path, monkeypatch):
    conn = seed_db(tmp_path, monkeypatch)
    logged = service.log_solve(conn, 1, "clean", CODE, today=date(2026, 9, 1))
    review_with(conn, monkeypatch, logged.solution_id, FEEDBACK)
    monkeypatch.setattr("coach.llm.parse", lambda *a, **kw: pytest.fail("a stored review was re-bought"))
    changes = conn.total_changes

    result = service.review_solution_now(conn, logged.solution_id, service.get_problem(conn, 1), CODE)

    assert result.cached and result.effect is None
    assert conn.total_changes == changes
    assert stored_schedule(conn) == (date(2026, 9, 4), 0, 1)


@pytest.mark.parametrize("reviewed_before", [False, True])
def test_a_reschedule_that_fails_rolls_back_the_review(tmp_path, monkeypatch, reviewed_before):
    """Saved together or not at all: a review the schedule never saw is the split this
    change removes. A refresh that fails keeps the review it would have replaced."""
    conn = seed_db(tmp_path, monkeypatch)
    logged = service.log_solve(conn, 1, "clean", CODE, today=date(2026, 9, 1))
    if reviewed_before:
        review_with(conn, monkeypatch, logged.solution_id, FEEDBACK)
    before = (review.load(conn, logged.solution_id), stored_schedule(conn))

    def fail(graded):
        raise RuntimeError("replay failed")

    monkeypatch.setattr("coach.scheduler.replay", fail)
    with pytest.raises(RuntimeError):
        review_with(conn, monkeypatch, logged.solution_id, OPTIMAL_REVIEW, refresh=True)

    assert (review.load(conn, logged.solution_id), stored_schedule(conn)) == before


def test_an_unavailable_model_leaves_the_review_and_schedule_alone(tmp_path, monkeypatch):
    conn = seed_db(tmp_path, monkeypatch)
    logged = service.log_solve(conn, 1, "clean", CODE, today=date(2026, 9, 1))
    review_with(conn, monkeypatch, logged.solution_id, FEEDBACK)

    def unavailable(*args, **kw):
        raise llm.LLMUnavailable("ANTHROPIC_API_KEY is not set")

    monkeypatch.setattr("coach.llm.parse", unavailable)
    result = service.review_solution_now(
        conn, logged.solution_id, service.get_problem(conn, 1), CODE, refresh=True
    )

    assert result.skipped and result.effect is None
    assert review.load(conn, logged.solution_id) == FEEDBACK
    assert stored_schedule(conn) == (date(2026, 9, 4), 0, 1)


def test_a_solve_logged_while_the_review_runs_is_in_the_schedule(tmp_path, monkeypatch):
    """The model call takes ~25s. The replay runs after it, so a solve logged from another
    request in the meantime is part of the schedule instead of being overwritten."""
    conn = seed_db(tmp_path, monkeypatch)
    logged = service.log_solve(conn, 1, "clean", CODE, today=date(2026, 9, 1))

    def slow_review(prompt, output_format, **kw):
        other = db.connect()
        service.log_solve(other, 1, "clean", CODE, today=date(2026, 9, 8))
        other.close()
        return FEEDBACK

    monkeypatch.setattr("coach.llm.parse", slow_review)
    result = service.review_solution_now(conn, logged.solution_id, service.get_problem(conn, 1), CODE)

    assert stored_schedule(conn) == (date(2026, 9, 15), 1, 1)
    assert result.effect.latest_attempt_date == date(2026, 9, 8)


def test_problem_content_is_fetched_once_and_cached_in_the_row(tmp_path, monkeypatch):
    conn = seed_db(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(
        "coach.catalog.fetch_content",
        lambda slug: calls.append(slug) or "2 <= nums.length <= 10^4",
    )

    first = service.problem_content(conn, service.get_problem(conn, 1))
    second = service.problem_content(conn, service.get_problem(conn, 1))

    assert first == second == "2 <= nums.length <= 10^4"
    assert calls == ["two-sum"]  # fetched once - the second call read the cached row


def test_problem_content_is_never_fetched_for_a_paid_only_problem(tmp_path, monkeypatch):
    conn = seed_db(
        tmp_path,
        monkeypatch,
        problems=[{**TWO_SUM[0], "paid_only": 1}],
    )
    monkeypatch.setattr(
        "coach.catalog.fetch_content", lambda slug: pytest.fail("paid-only content was fetched")
    )

    assert service.problem_content(conn, service.get_problem(conn, 1)) is None


def test_problem_content_degrades_to_none_when_the_fetch_fails(tmp_path, monkeypatch):
    conn = seed_db(tmp_path, monkeypatch)

    def unreachable(slug):
        raise httpx.ConnectError("no route to leetcode.com")

    monkeypatch.setattr("coach.catalog.fetch_content", unreachable)

    assert service.problem_content(conn, service.get_problem(conn, 1)) is None
    assert service.get_problem(conn, 1)["content"] is None


def test_a_review_prompt_includes_the_fetched_problem_statement(tmp_path, monkeypatch):
    conn = seed_db(tmp_path, monkeypatch)
    logged = service.log_solve(conn, 1, "clean", CODE, today=date(2026, 9, 1))
    monkeypatch.setattr(
        "coach.catalog.fetch_content", lambda slug: "2 <= nums.length <= 10^4"
    )
    seen_prompts = []
    monkeypatch.setattr(
        "coach.llm.parse",
        lambda prompt, output_format, **kw: seen_prompts.append(prompt) or FEEDBACK,
    )

    service.review_solution_now(conn, logged.solution_id, service.get_problem(conn, 1), CODE)

    assert "2 <= nums.length <= 10^4" in seen_prompts[0]


def test_a_late_bug_review_puts_the_problem_on_the_plan_with_its_reason(tmp_path, monkeypatch):
    """Reviewed days after a clean solve due 09-08: the lapse fell due on 09-04, so on 09-06
    the problem is already owed - and the plan says why instead of a bare date."""
    conn = seed_db(tmp_path, monkeypatch)
    logged = service.log_solve(conn, 1, "clean", CODE, today=date(2026, 9, 1))
    plan_day = date(2026, 9, 6)
    before = service.daily_plan(conn, plan_day, config.SECTION_LIMIT).sections
    assert (before.due, before.approach, before.weak) == ([], [], [])

    review_with(conn, monkeypatch, logged.solution_id, FEEDBACK)

    due = service.daily_plan(conn, plan_day, config.SECTION_LIMIT).sections.due
    assert [(i.number, [(r.kind, r.text) for r in i.reasons]) for i in due] == [
        (1, [("review", "re-solve: review reported a bug")])
    ]


def test_enrich_solution_now_reports_llm_degradation(tmp_path, monkeypatch):
    conn = seed_db(tmp_path, monkeypatch)
    result = service.log_solve(conn, 1, "clean", CODE)
    problem = service.get_problem(conn, 1)

    e = service.enrich_solution_now(conn, result.solution_id, problem, CODE)

    assert e.main_patterns == []
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

    assert e.main_patterns == ["hashmap"]
    assert e.embed_skipped
    assert e.neighbors == []
    # the tags still landed - only the vector is missing
    assert conn.execute("SELECT COUNT(*) FROM enrichments").fetchone()[0] == 1


BEST_TIME = {
    "number": 121,
    "slug": "best-time-to-buy-and-sell-stock",
    "title": "Best Time to Buy and Sell Stock",
    "difficulty": "Easy",
    "official_tags": '["array", "dynamic-programming"]',
    "paid_only": 0,
}


def store_embedded_solve(conn, number, vector, pattern, key_trick):
    """A tagged, embedded solve stored directly, as logging and `coach enrich` leave one."""
    solution_id = conn.execute(
        "INSERT INTO solutions (problem_number, code, created_at) VALUES (?, 'c', '2026-09-01')",
        (number,),
    ).lastrowid
    tag_solution(conn, solution_id, pattern, key_trick=key_trick)
    embed.store(conn, solution_id, np.array(vector, dtype=np.float32))


def test_a_neighbor_is_described_by_the_solve_that_matched(tmp_path, monkeypatch):
    """A problem keeps a vector per solve so it can be found through every approach it was
    solved with, so it must be shown through that approach too: describing a hit by its
    problem's latest solve labelled a match found through the DP solve as greedy."""
    conn = seed_db(tmp_path, monkeypatch, [*TWO_SUM, BEST_TIME])
    store_embedded_solve(conn, 121, [1.0, 0.0, 0.0], "dp-1d", "Best profit ending at each day.")
    store_embedded_solve(conn, 121, [0.0, 1.0, 0.0], "greedy", "Track the running minimum price.")
    conn.commit()
    dp = ENRICHMENT.model_copy(update={"main_patterns": ["dp-1d"]})
    monkeypatch.setattr("coach.llm.parse", lambda prompt, output_format, **kw: dp)
    monkeypatch.setattr("coach.embed.encode", fake_encode)
    result = service.log_solve(conn, 1, "clean", CODE)

    e = service.enrich_solution_now(conn, result.solution_id, service.get_problem(conn, 1), CODE)

    assert [(n.number, n.main_patterns, n.key_trick) for n in e.neighbors] == [
        (121, ["dp-1d"], "Best profit ending at each day.")
    ]


def test_enrich_solution_now_flags_off_pattern(tmp_path, monkeypatch):
    conn = seed_db(tmp_path, monkeypatch)
    off = ENRICHMENT.model_copy(
        update={"main_patterns": ["prefix-sum"], "intended_pattern": "dp-1d"}
    )
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
    alternate = ENRICHMENT.model_copy(update={"main_patterns": ["two-pointers"]})
    monkeypatch.setattr("coach.llm.parse", lambda prompt, output_format, **kw: alternate)
    monkeypatch.setattr("coach.embed.encode", fake_encode)
    result = service.log_solve(conn, 1, "clean", CODE)

    e = service.enrich_solution_now(conn, result.solution_id, service.get_problem(conn, 1), CODE)

    assert e.off_pattern is False
    # the note still points at the approach that went unpractised
    assert e.also_solvable_with == ["hashmap"]
    assert e.intended_secondary_patterns == ["two-pointers"]
    assert corrections.owed(history.load(conn)) == []


def test_enrich_solution_now_carries_both_signals_when_embedding_fails(tmp_path, monkeypatch):
    """The early return path must not drop the new fields."""
    conn = seed_db(tmp_path, monkeypatch)
    off = ENRICHMENT.model_copy(
        update={"main_patterns": ["prefix-sum"], "intended_pattern": "dp-1d"}
    )
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
        conn, monkeypatch, main_patterns=["two-pointers"], intended_secondary_patterns=[]
    )

    assert e.off_pattern is False
    assert e.intended_secondary_patterns == ["two-pointers"]
    assert e.also_solvable_with == ["hashmap"]
    # the response, the stored problem and the planner all read one set
    assert (e.intended_pattern, e.intended_secondary_patterns) == service.problem_canonical(
        service.get_problem(conn, 1)
    )
    analysis = weekly_analyze.analyze(conn, date.today())
    assert (analysis["corrections_due"], corrections.owed(history.load(conn))) == ([], [])


def test_enrich_solution_now_keeps_a_demoted_central_pattern_canonical(tmp_path, monkeypatch):
    conn = seed_db(tmp_path, monkeypatch)

    e = enrich_against_stored_canonical(
        conn,
        monkeypatch,
        main_patterns=["hashmap"],
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


def log_tagged(conn, monkeypatch, number, outcome="clean", **tags):
    """Log a solve of `number`, tagged as ENRICHMENT with `tags` overriding it."""
    e = ENRICHMENT.model_copy(update=tags)
    monkeypatch.setattr("coach.llm.parse", lambda prompt, output_format, **kw: e)
    monkeypatch.setattr("coach.embed.encode", fake_encode)
    result = service.log_solve(conn, number, outcome, CODE)
    service.enrich_solution_now(conn, result.solution_id, service.get_problem(conn, number), CODE)


def test_pattern_table_credits_a_problem_once_per_approach(tmp_path, monkeypatch):
    conn = seed_db(tmp_path, monkeypatch)

    # one problem solved three times: two approaches, the second one repeated
    for pattern in ("prefix-sum", "hashmap", "hashmap"):
        log_tagged(conn, monkeypatch, 1, main_patterns=[pattern])

    # both approaches counted, the repeated one still one problem - but two attempts
    assert service.pattern_table(conn) == [
        {"pattern": "hashmap", "solved": 1, "score": 5.0, "attempts": 2, "rough": 0},
        {"pattern": "prefix-sum", "solved": 1, "score": 5.0, "attempts": 1, "rough": 0},
    ]


def test_pattern_table_leaves_out_patterns_only_used_as_a_secondary(tmp_path, monkeypatch):
    """A secondary is a step the solve leaned on, not a pattern it practiced: it has
    nothing to be scored on, so it gets no row rather than a row of dashes."""
    conn = seed_db(tmp_path, monkeypatch)
    log_tagged(conn, monkeypatch, 1, "struggled", secondary_patterns=["two-pointers"])

    assert service.pattern_table(conn) == [
        {"pattern": "hashmap", "solved": 1, "score": 3.0, "attempts": 1, "rough": 1},
    ]


def test_pattern_table_does_not_count_a_secondary_toward_solved(tmp_path, monkeypatch):
    """Every column of a row describes the same solves. two-pointers led only the
    3Sum solve, so it has solved one problem - not two beside one attempt."""
    conn = seed_db(tmp_path, monkeypatch, TWO_SUM + [THREE_SUM])
    log_tagged(conn, monkeypatch, 1, secondary_patterns=["two-pointers"])
    log_tagged(conn, monkeypatch, 15, main_patterns=["two-pointers"])

    table = {row["pattern"]: row for row in service.pattern_table(conn)}

    assert table["two-pointers"] == {
        "pattern": "two-pointers", "solved": 1, "score": 5.0, "attempts": 1, "rough": 0,
    }


def test_pattern_table_counts_a_problem_under_each_of_its_main_patterns(tmp_path, monkeypatch):
    conn = seed_db(tmp_path, monkeypatch, TWO_SUM + [THREE_SUM])
    log_tagged(conn, monkeypatch, 1, "struggled", main_patterns=["hashmap", "two-pointers"])
    log_tagged(conn, monkeypatch, 15, main_patterns=["two-pointers"])

    # two-pointers: the struggled Two Sum solve at 3.0, then 3Sum's 5.0 folded in at alpha 0.2
    assert service.pattern_table(conn) == [
        {"pattern": "two-pointers", "solved": 2, "score": pytest.approx(3.4),
         "attempts": 2, "rough": 1},
        {"pattern": "hashmap", "solved": 1, "score": 3.0, "attempts": 1, "rough": 1},
    ]


# Enough problems for one pattern to span mastery.WEAK_MIN_PROBLEMS of them and be judged.
ENOUGH_PROBLEMS = TWO_SUM + [
    {**TWO_SUM[0], "number": n, "slug": f"problem-{n}", "title": f"Problem {n}"}
    for n in range(2, mastery.WEAK_MIN_PROBLEMS + 1)
]


def log_and_enrich(conn, monkeypatch, outcome, pattern="hashmap", number=1):
    e = ENRICHMENT.model_copy(update={"main_patterns": [pattern], "intended_pattern": pattern})
    monkeypatch.setattr("coach.llm.parse", lambda prompt, output_format, _e=e, **kw: _e)
    monkeypatch.setattr("coach.embed.encode", fake_encode)
    r = service.log_solve(conn, number, outcome, CODE)
    return service.enrich_solution_now(conn, r.solution_id, service.get_problem(conn, number), CODE)


def test_pattern_standings_are_empty_with_nothing_to_stand_on(tmp_path, monkeypatch):
    """No patterns means enrichment was skipped; a pattern never practiced has no record."""
    conn = seed_db(tmp_path, monkeypatch)

    assert service.pattern_standings(conn, []) == []
    assert service.pattern_standings(conn, ["hashmap"]) == []


def test_pattern_standings_withhold_a_verdict_on_a_first_attempt(tmp_path, monkeypatch):
    conn = seed_db(tmp_path, monkeypatch)
    log_and_enrich(conn, monkeypatch, "failed")

    assert service.pattern_standings(conn, ["hashmap"]) == [
        service.PatternStanding(
            pattern="hashmap", solved=1, attempts=1, struggle_rate=1.0, score=1.0,
            weak=False, enough_data=False,
        )
    ]


def test_pattern_standings_withhold_a_verdict_over_many_attempts_on_few_problems(
    tmp_path, monkeypatch
):
    """Seven failures would have been judged weak by attempts; four problems are too few."""
    conn = seed_db(tmp_path, monkeypatch, ENOUGH_PROBLEMS)
    for number in (1, 1, 1, 2, 2, 3, 4):
        log_and_enrich(conn, monkeypatch, "failed", number=number)

    assert service.pattern_standings(conn, ["hashmap"]) == [
        service.PatternStanding(
            pattern="hashmap", solved=4, attempts=7, struggle_rate=1.0, score=1.0,
            weak=False, enough_data=False,
        )
    ]


def test_pattern_standings_call_a_pattern_weak_once_there_is_data(tmp_path, monkeypatch):
    conn = seed_db(tmp_path, monkeypatch, ENOUGH_PROBLEMS)
    for number in range(1, 6):
        log_and_enrich(conn, monkeypatch, "failed", number=number)

    assert service.pattern_standings(conn, ["hashmap"]) == [
        service.PatternStanding(
            pattern="hashmap", solved=5, attempts=5, struggle_rate=1.0, score=1.0,
            weak=True, enough_data=True,
        )
    ]


def test_pattern_standings_stay_clear_of_weak_on_clean_solves(tmp_path, monkeypatch):
    conn = seed_db(tmp_path, monkeypatch, ENOUGH_PROBLEMS)
    for number in range(1, 6):
        log_and_enrich(conn, monkeypatch, "clean", number=number)

    assert service.pattern_standings(conn, ["hashmap"]) == [
        service.PatternStanding(
            pattern="hashmap", solved=5, attempts=5, struggle_rate=0.0, score=5.0,
            weak=False, enough_data=True,
        )
    ]


def test_pattern_standings_separate_struggling_from_failing(tmp_path, monkeypatch):
    """Same 100% struggle rate as the weak case above, a very different score."""
    conn = seed_db(tmp_path, monkeypatch, ENOUGH_PROBLEMS)
    for number in range(1, 6):
        log_and_enrich(conn, monkeypatch, "struggled", number=number)

    [standing] = service.pattern_standings(conn, ["hashmap"])
    assert standing.struggle_rate == 1.0
    assert standing.score == pytest.approx(3.0)
    assert standing.weak is False


def test_pattern_standings_report_every_main_pattern_of_the_solve(tmp_path, monkeypatch):
    conn = seed_db(tmp_path, monkeypatch)
    log_tagged(conn, monkeypatch, 1, "failed", main_patterns=["hashmap", "two-pointers"])

    standings = service.pattern_standings(conn, ["hashmap", "two-pointers"])

    assert [(s.pattern, s.attempts, s.score) for s in standings] == [
        ("hashmap", 1, 1.0),
        ("two-pointers", 1, 1.0),
    ]


def test_a_stored_review_pulls_the_pattern_score_down(tmp_path, monkeypatch):
    """A solve can feel clean and still carry a bug - that is what the review adds."""
    conn = seed_db(tmp_path, monkeypatch)
    for _ in range(4):
        log_and_enrich(conn, monkeypatch, "clean")
    result = service.log_solve(conn, 1, "clean", CODE)
    service.enrich_solution_now(conn, result.solution_id, service.get_problem(conn, 1), CODE)
    assert service.pattern_standings(conn, ["hashmap"])[0].score == 5.0

    monkeypatch.setattr("coach.llm.parse", lambda prompt, output_format, **kw: FEEDBACK)
    service.review_solution_now(
        conn, result.solution_id, service.get_problem(conn, 1), CODE, refresh=True
    )

    # the reported bug holds that solve at 1, folded in at alpha 0.2: 0.8*5 + 0.2*1
    assert service.pattern_standings(conn, ["hashmap"])[0].score == pytest.approx(4.2)


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

    reviewed = pytest.approx(4.2)  # four clean solves, then the bug-capped 1 folded in
    assert service.pattern_table(conn)[0]["score"] == reviewed
    assert service.pattern_standings(conn, ["hashmap"], today)[0].score == reviewed
    plan = service.daily_plan(conn, today, config.SECTION_LIMIT)
    assert plan.analysis["patterns"][0]["score"] == reviewed
    assert service.weekly_review(conn, today).patterns[0].score == reviewed


def test_mastery_readers_write_nothing_and_call_no_model(tmp_path, monkeypatch):
    """Every page load reads mastery and approach practice, so reading them must stay free."""
    conn = seed_db(tmp_path, monkeypatch)
    for _ in range(5):
        log_and_enrich(conn, monkeypatch, "failed")
    log_tagged(conn, monkeypatch, 1, main_patterns=["prefix-sum"], intended_pattern="dp-1d")
    monkeypatch.setattr(
        "coach.llm.parse", lambda *args, **kw: pytest.fail("a page reader called the model")
    )
    today = date.today()
    before = conn.total_changes

    service.pattern_table(conn)
    service.pattern_standings(conn, ["hashmap"], today)
    service.daily_plan(conn, today, config.SECTION_LIMIT)
    service.weekly_review(conn, today)
    service.solution_history(conn, 1)
    assert service.practice_dates(conn, 1).correction is not None

    assert conn.total_changes == before


def log_on(conn, monkeypatch, day, outcome, *main_patterns):
    """Log a Two Sum solve on `day` and tag it, against the canonical set dp-1d + two-pointers."""
    answer = ENRICHMENT.model_copy(
        update={"main_patterns": list(main_patterns), "intended_pattern": "dp-1d"}
    )
    monkeypatch.setattr("coach.llm.parse", lambda prompt, output_format, **kw: answer)
    logged = service.log_solve(conn, 1, outcome, CODE, today=day)
    service.tag_solution_now(conn, logged.solution_id, service.get_problem(conn, 1), CODE)
    return logged


def test_practice_dates_keep_the_review_and_approach_practice_apart(tmp_path, monkeypatch):
    """A clean wrong-approach solve: SM-2 wants it back in a week, approach practice in three
    days. Both dates are kept, and the next practice is the earlier of them."""
    conn = seed_db(tmp_path, monkeypatch)
    logged = log_on(conn, monkeypatch, date(2026, 9, 12), "clean", "prefix-sum")

    dates = service.practice_dates(conn, 1, logged.attempt_id)

    assert dates.review_due == date(2026, 9, 19)
    assert (dates.correction.due, dates.correction.reason) == (date(2026, 9, 15), "wrong-approach")
    assert dates.next_practice == date(2026, 9, 15)
    assert dates.completed is False


def test_practice_dates_say_which_log_completed_approach_practice(tmp_path, monkeypatch):
    """The 09-15 failure keeps it owed, and so does the clean retry straight after it - SM-2
    lapses that day too, so both dates meet on 09-18. The success on 09-18 completes it."""
    conn = seed_db(tmp_path, monkeypatch)

    def after(day, outcome, *patterns):
        logged = log_on(conn, monkeypatch, day, outcome, *patterns)
        return service.practice_dates(conn, 1, logged.attempt_id)

    after(date(2026, 9, 12), "clean", "prefix-sum")
    failed = after(date(2026, 9, 15), "failed", "dp-1d")
    retried = after(date(2026, 9, 15), "clean", "dp-1d")
    succeeded = after(date(2026, 9, 18), "clean", "dp-1d")

    assert [(d.review_due, d.correction.due, d.completed) for d in (failed, retried)] == [
        (date(2026, 9, 18), date(2026, 9, 18), False),
        (date(2026, 9, 18), date(2026, 9, 18), False),
    ]
    assert (succeeded.correction, succeeded.completed) == (None, True)
    assert succeeded.next_practice == succeeded.review_due == date(2026, 9, 25)


def test_approach_practice_completes_without_advancing_the_review(tmp_path, monkeypatch):
    """The two dates answer different questions. On 09-15 the accepted approach completes
    approach practice, but the review is not due until 09-19, so it stays there - where it
    used to step to 09-29 as if a second week of remembering had been shown."""
    conn = seed_db(tmp_path, monkeypatch)
    log_on(conn, monkeypatch, date(2026, 9, 12), "clean", "prefix-sum")

    logged = log_on(conn, monkeypatch, date(2026, 9, 15), "clean", "dp-1d")
    dates = service.practice_dates(conn, 1, logged.attempt_id)

    assert (dates.correction, dates.completed) == (None, True)
    assert (dates.review_due, logged.counted_as_review) == (date(2026, 9, 19), False)


def test_practice_dates_owe_nothing_before_any_attempt(tmp_path, monkeypatch):
    conn = seed_db(tmp_path, monkeypatch)

    dates = service.practice_dates(conn, 1)

    assert (dates.review_due, dates.correction, dates.next_practice, dates.completed) == (
        None,
        None,
        None,
        False,
    )


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
        "by_difficulty": {"Easy": 1, "Medium": 1, "Hard": 0},
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
    week = weekly_collect.window(history.load(conn), today)

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
    assert history["solves"][0]["main_patterns"] == ["hashmap"]
    assert history["solves"][1]["main_patterns"] == []  # logged before enrichment ran


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
    assert rows[0]["main_patterns"] == ["hashmap"]


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
        tag_solution(conn, solution_id, pattern)
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
    assert review.attempts[0]["main_patterns"] == []
    assert review.patterns == []


def test_weekly_review_lists_every_main_pattern_of_a_solve(tmp_path, monkeypatch):
    conn = seed_db(tmp_path, monkeypatch)
    solution_id = scored_attempt(conn, WEEK_TODAY, "clean", pattern=None)
    tag_solution(conn, solution_id, "hashmap", "two-pointers")

    review = service.weekly_review(conn, WEEK_TODAY)

    assert review.attempts[0]["main_patterns"] == ["hashmap", "two-pointers"]
    assert [(p.pattern, p.attempts_week) for p in review.patterns] == [
        ("hashmap", 1),
        ("two-pointers", 1),
    ]


def test_weekly_review_says_too_early_below_the_problem_floor(tmp_path, monkeypatch):
    """Six attempts, but on four problems: the floor counts problems, not attempts."""
    conn = seed_db(tmp_path, monkeypatch, ENOUGH_PROBLEMS)
    for day, number in enumerate((1, 1, 2, 2, 3, 4)):
        scored_attempt(conn, WEEK_TODAY - timedelta(days=day), "failed", number=number)

    p = service.weekly_review(conn, WEEK_TODAY).patterns[0]

    assert (p.attempts_total, p.solved_total) == (6, 4)
    assert p.solved_total < mastery.WEAK_MIN_PROBLEMS
    assert p.standing == "too-early"


def test_weekly_review_standing_tracks_the_analysis_verdict(tmp_path, monkeypatch):
    """weak is only ever membership in analysis["weak_patterns"] - never a
    threshold re-derived here, which is how the two definitions drift apart."""
    conn = seed_db(tmp_path, monkeypatch, ENOUGH_PROBLEMS)
    for day in range(5):
        scored_attempt(conn, WEEK_TODAY - timedelta(days=day), "failed", number=day + 1)

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
    conn = seed_db(tmp_path, monkeypatch, ENOUGH_PROBLEMS)
    for day in range(5):
        day_before = WEEK_TODAY - timedelta(days=day)
        scored_attempt(conn, day_before, "failed", pattern="dp-1d", number=day + 1)
        scored_attempt(conn, day_before, "clean", pattern="hashmap", number=day + 1)
    scored_attempt(conn, WEEK_TODAY, "clean", pattern="graphs")

    review = service.weekly_review(conn, WEEK_TODAY)

    assert [(p.pattern, p.standing) for p in review.patterns] == [
        ("dp-1d", "weak"),
        ("hashmap", "on-track"),
        ("graphs", "too-early"),
    ]


def test_weekly_review_loads_history_once(tmp_path, monkeypatch):
    """Current mastery and the week's baseline come from one read, not two replays.

    history.load() is the shared read now - mastery, corrections, findings and the
    weekly window are all pure over the same attempts weekly_review() loads once.
    """
    conn = seed_db(tmp_path, monkeypatch)
    scored_attempt(conn, WEEK_TODAY - timedelta(days=10), "failed")
    scored_attempt(conn, WEEK_TODAY, "clean")
    loads = []
    real = history.load
    monkeypatch.setattr(
        history, "load", lambda conn, number=None: loads.append(conn) or real(conn, number)
    )

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

    due = service.daily_plan(conn, today, limit=4).sections.due

    assert [(i.number, [(r.kind, r.text) for r in i.reasons]) for i in due] == [
        (1, [("review", f"review due {today.isoformat()}")])
    ]


def test_approach_practice_waits_three_days_after_the_solve_that_opened_it(tmp_path, monkeypatch):
    """Logged off-pattern on 09-12: the problem stays off the Daily Plan for three days and is
    owed on 09-15, while its SM-2 review keeps its own date a week out."""
    conn = seed_db(tmp_path, monkeypatch)
    day = date(2026, 9, 12)
    off = ENRICHMENT.model_copy(
        update={"main_patterns": ["prefix-sum"], "intended_pattern": "dp-1d"}
    )
    monkeypatch.setattr("coach.llm.parse", lambda prompt, output_format, **kw: off)
    monkeypatch.setattr("coach.embed.encode", fake_encode)
    logged = service.log_solve(conn, 1, "clean", CODE, today=day)
    service.enrich_solution_now(conn, logged.solution_id, service.get_problem(conn, 1), CODE)

    def planned(offset):
        s = service.daily_plan(conn, day + timedelta(days=offset), config.SECTION_LIMIT).sections
        return [(i.number, [r.kind for r in i.reasons]) for i in [*s.due, *s.approach, *s.weak]]

    assert [planned(offset) for offset in range(3)] == [[], [], []]
    assert planned(3) == [(1, ["re-solve"])]
    assert logged.next_due == date(2026, 9, 19)


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
