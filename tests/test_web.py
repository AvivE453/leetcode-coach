from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import numpy as np
import pytest
from conftest import CODE, seed_db
from fastapi.testclient import TestClient

from coach import config, db, enrich, mastery, review, service
from coach.web.app import app
from coach.weekly import analyze as weekly_analyze

ENRICHMENT = enrich.Enrichment(
    main_patterns=["hashmap"],
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

PROBLEMS = [
    {
        "number": 1,
        "slug": "two-sum",
        "title": "Two Sum",
        "difficulty": "Easy",
        "official_tags": '["array", "hash-table"]',
        "paid_only": 0,
    },
    {
        "number": 15,
        "slug": "3sum",
        "title": "3Sum",
        "difficulty": "Medium",
        "official_tags": '["array", "two-pointers"]',
        "paid_only": 0,
    },
]


def fake_encode(texts):
    return np.tile(np.array([1.0, 0.0, 0.0], dtype=np.float32), (len(texts), 1))


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A TestClient bound to a scratch database - never data/coach.db.

    Two problems rather than conftest's one, both on the curriculum, so the plan
    endpoint has something unsolved to rank behind a solved one.
    """
    conn = seed_db(tmp_path, monkeypatch, PROBLEMS)
    conn.execute("UPDATE problems SET in_blind75 = 1")
    conn.commit()
    conn.close()
    with TestClient(app) as c:
        yield c


def enriched(monkeypatch, **overrides):
    e = ENRICHMENT.model_copy(update=overrides) if overrides else ENRICHMENT
    monkeypatch.setattr("coach.llm.parse", lambda prompt, output_format, **kw: e)
    monkeypatch.setattr("coach.embed.encode", fake_encode)


def add_filler_problems(count) -> list[int]:
    """Untagged, off-curriculum problems, so a pattern can span enough problems to be
    judged without giving the plan anything new to rank. Returns their numbers."""
    numbers = [1000 + n for n in range(count)]
    conn = db.connect()
    db.upsert_problems(
        conn,
        [
            {"number": n, "slug": f"filler-{n}", "title": f"Filler {n}", "difficulty": "Easy",
             "official_tags": "[]", "paid_only": 0}
            for n in numbers
        ],
    )
    conn.close()
    return numbers


def test_stats_endpoint(client):
    s = client.get("/api/stats").json()
    assert s["catalog"] == 2
    assert s["solved"] == 0
    assert s["curriculum"]["blind75"] == {"done": 0, "total": 2}
    assert s["db"].endswith("coach.db")


def test_log_endpoint_stores_and_enriches(client, monkeypatch):
    enriched(monkeypatch)

    res = client.post("/api/log", json={"number": 1, "outcome": "struggled", "code": CODE})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["title"] == "Two Sum"
    assert body["counted_as_review"] is True
    assert body["enrichment"]["status"] == "ok"
    assert body["enrichment"]["main_patterns"] == ["hashmap"]
    assert body["enrichment"]["off_pattern"] is False

    conn = db.connect()
    assert conn.execute("SELECT outcome FROM attempts").fetchone()["outcome"] == "struggled"
    assert conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0] == 1
    assert client.get("/api/stats").json()["solved"] == 1


def test_log_endpoint_flags_off_pattern_solves(client, monkeypatch):
    enriched(monkeypatch, main_patterns=["prefix-sum"], intended_pattern="dp-1d")

    body = client.post("/api/log", json={"number": 1, "outcome": "clean", "code": CODE}).json()

    assert body["enrichment"]["off_pattern"] is True
    assert body["enrichment"]["intended_pattern"] == "dp-1d"
    assert body["enrichment"]["intended_secondary_patterns"] == ["two-pointers"]
    assert body["enrichment"]["also_solvable_with"] == ["dp-1d", "two-pointers"]


def test_log_endpoint_accepts_a_canonical_alternate_approach(client, monkeypatch):
    """An alternate canonical route is not off-pattern, but the unused central
    approach is still worth mentioning."""
    enriched(monkeypatch, main_patterns=["two-pointers"], intended_pattern="hashmap")

    body = client.post("/api/log", json={"number": 1, "outcome": "clean", "code": CODE}).json()

    assert body["enrichment"]["off_pattern"] is False
    assert body["enrichment"]["also_solvable_with"] == ["hashmap"]


def test_log_endpoint_agrees_with_the_stored_canonical_set_and_the_plan(client, monkeypatch):
    """A later answer that forgets an accepted approach must not re-flag a solve that
    used it: the log response, the solutions page and the plan read one canonical set."""
    enriched(monkeypatch)  # stores hashmap + two-pointers
    client.post("/api/log", json={"number": 1, "outcome": "clean", "code": CODE})

    enriched(monkeypatch, main_patterns=["two-pointers"], intended_secondary_patterns=[])
    body = client.post("/api/log", json={"number": 1, "outcome": "clean", "code": CODE}).json()

    enrichment = body["enrichment"]
    stored = client.get("/api/solutions/1").json()["intended_secondary_patterns"]
    topics = client.get("/api/plan").json()["topics"]
    assert enrichment["off_pattern"] is False
    assert enrichment["intended_secondary_patterns"] == stored == ["two-pointers"]
    assert (topics["corrections_due"], topics["corrections_upcoming"]) == ([], [])


def test_solution_history_endpoint_carries_the_canonical_note(client, monkeypatch):
    enriched(monkeypatch)
    client.post("/api/log", json={"number": 1, "outcome": "clean", "code": CODE})

    body = client.get("/api/solutions/1").json()

    assert body["intended_secondary_patterns"] == ["two-pointers"]
    assert body["solves"][0]["also_solvable_with"] == ["two-pointers"]
    assert body["solves"][0]["secondary_patterns"] == []
    assert body["solves"][0]["main_patterns"] == ["hashmap"]
    assert client.get("/api/solutions").json()["problems"][0]["main_patterns"] == ["hashmap"]


def test_log_endpoint_degrades_without_an_api_key(client):
    """No key must never cost the user their solve - it is saved, untagged."""
    res = client.post("/api/log", json={"number": 1, "outcome": "clean", "code": CODE})
    assert res.status_code == 200, res.text
    enrichment = res.json()["enrichment"]
    assert enrichment["status"] == "skipped"
    assert "ANTHROPIC_API_KEY" in enrichment["reason"]

    conn = db.connect()
    assert conn.execute("SELECT COUNT(*) FROM solutions").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM enrichments").fetchone()[0] == 0


def test_log_endpoint_withholds_a_standing_on_a_first_solve(client, monkeypatch):
    enriched(monkeypatch)

    body = client.post("/api/log", json={"number": 1, "outcome": "failed", "code": CODE}).json()

    assert body["pattern_standings"] == [
        {
            "pattern": "hashmap",
            "solved": 1,
            "attempts": 1,
            "struggle_rate": 1.0,
            "score": 1.0,
            "weak": False,
            "enough_data": False,
        }
    ]


def test_log_endpoint_reports_a_weak_pattern(client, monkeypatch):
    enriched(monkeypatch)
    *earlier, last = [1, 15, *add_filler_problems(3)]
    for number in earlier:
        client.post("/api/log", json={"number": number, "outcome": "failed", "code": CODE})

    body = client.post("/api/log", json={"number": last, "outcome": "failed", "code": CODE}).json()

    assert body["pattern_standings"] == [
        {
            "pattern": "hashmap",
            "solved": 5,
            "attempts": 5,
            "struggle_rate": 1.0,
            "score": 1.0,
            "weak": True,
            "enough_data": True,
        }
    ]


def test_log_endpoint_reports_a_standing_for_every_main_pattern(client, monkeypatch):
    enriched(monkeypatch, main_patterns=["hashmap", "two-pointers"])

    body = client.post("/api/log", json={"number": 1, "outcome": "failed", "code": CODE}).json()

    assert body["enrichment"]["main_patterns"] == ["hashmap", "two-pointers"]
    assert [(s["pattern"], s["score"]) for s in body["pattern_standings"]] == [
        ("hashmap", 1.0),
        ("two-pointers", 1.0),
    ]


def test_log_endpoint_lists_similar_solves_with_their_main_patterns(client, monkeypatch):
    enriched(monkeypatch, main_patterns=["hashmap", "two-pointers"])
    client.post("/api/log", json={"number": 15, "outcome": "clean", "code": CODE})
    enriched(monkeypatch)

    body = client.post("/api/log", json={"number": 1, "outcome": "clean", "code": CODE}).json()

    # 3Sum shares hashmap with this solve, so it is a neighbor - shown with both its mains
    assert [(n["number"], n["main_patterns"]) for n in body["enrichment"]["neighbors"]] == [
        (15, ["hashmap", "two-pointers"])
    ]


def test_log_endpoint_has_no_standing_without_enrichment(client):
    body = client.post("/api/log", json={"number": 1, "outcome": "clean", "code": CODE}).json()

    assert body["enrichment"]["status"] == "skipped"
    assert body["pattern_standings"] == []


def test_log_endpoint_rejects_unknown_problem_and_empty_code(client):
    missing = client.post("/api/log", json={"number": 99999, "outcome": "clean", "code": CODE})
    assert missing.status_code == 404
    assert "not in the catalog" in missing.json()["detail"]

    blank = client.post("/api/log", json={"number": 1, "outcome": "clean", "code": "  \n"})
    assert blank.status_code == 400

    bad_outcome = client.post("/api/log", json={"number": 1, "outcome": "great", "code": CODE})
    assert bad_outcome.status_code == 422

    conn = db.connect()
    assert conn.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0


def test_patterns_endpoint_feeds_the_pattern_table(client, monkeypatch):
    enriched(monkeypatch)
    client.post("/api/log", json={"number": 1, "outcome": "clean", "code": CODE})
    client.post("/api/log", json={"number": 1, "outcome": "clean", "code": CODE})

    # two attempts on one problem is still one solved unit - but two attempts of practice
    assert client.get("/api/patterns").json() == {
        "patterns": [{"pattern": "hashmap", "solved": 1, "score": 5.0, "attempts": 2, "rough": 0}]
    }


def test_log_endpoint_stores_note_and_minutes(client):
    """The two optional form fields reach the page that shows each: the note on
    Solutions, the minutes on Weekly Review."""
    client.post(
        "/api/log",
        json={"number": 1, "outcome": "clean", "code": CODE, "minutes": 12, "note": "forgot the empty case"},
    )

    solve = client.get("/api/solutions/1").json()["solves"][0]
    assert (solve["minutes"], solve["note"]) == (12, "forgot the empty case")
    assert client.get("/api/weekly").json()["attempts"][0]["minutes"] == 12


def test_plan_endpoint_ranks_problems_and_stays_read_only(client, monkeypatch, tmp_path):
    enriched(monkeypatch)
    client.post("/api/log", json={"number": 1, "outcome": "clean", "code": CODE})

    # A fresh clean solve isn't due again for a week (see coach/scheduler.py),
    # so force it due now to exercise the "due outranks curriculum" ranking.
    conn = db.connect()
    conn.execute("UPDATE review_state SET next_due = date('now') WHERE problem_number = 1")
    conn.commit()
    conn.close()

    plan = client.get("/api/plan").json()

    # the due review outranks curriculum progression
    assert [(i["number"], [r["kind"] for r in i["reasons"]]) for i in plan["items"]] == [
        (1, ["review"]),
        (15, ["curriculum"]),
    ]
    assert plan["topics"] == {
        "weak": [],
        "stale": [],
        "corrections_due": [],
        "corrections_upcoming": [],
    }
    assert not (tmp_path / "reports").exists()


def test_plan_endpoint_labels_a_weak_pattern_pick(client, monkeypatch):
    """The one chip class no test reached: a pick made to practice a weak pattern.

    It is the branch furthest from the endpoint - a pattern has to go weak, and an
    unsolved problem has to carry the matching official tag - which is exactly why
    it went uncovered while the kind was recovered by parsing the reason sentence.
    """
    enriched(monkeypatch, main_patterns=["two-pointers"])
    for number in [1, *add_filler_problems(mastery.WEAK_MIN_PROBLEMS - 1)]:
        client.post("/api/log", json={"number": number, "outcome": "failed", "code": CODE})

    plan = client.get("/api/plan").json()

    assert plan["topics"]["weak"] == ["two-pointers"]
    # #15 is unsolved, on the curriculum, and officially tagged two-pointers.
    assert [(i["number"], i["reasons"]) for i in plan["items"]] == [
        (15, [{"kind": "weak-pattern", "text": "weak pattern: two-pointers"}])
    ]


def test_plan_endpoint_only_counts_reviews_due_today(client, monkeypatch):
    """The page is /plan's "Today", not the old weekly view: a review owed in
    three days must not appear, even though the planner's default lookahead would show it."""
    enriched(monkeypatch)
    client.post("/api/log", json={"number": 1, "outcome": "clean", "code": CODE})

    conn = db.connect()
    conn.execute(
        "UPDATE review_state SET next_due = date('now', '+3 days') WHERE problem_number = 1"
    )
    conn.commit()
    conn.close()

    plan = client.get("/api/plan").json()

    assert plan["due_count"] == 0
    assert 1 not in [i["number"] for i in plan["items"]]


def test_plan_endpoint_defaults_to_the_daily_target(client, monkeypatch):
    assert client.get("/api/plan").json()["target"] == config.DAILY_TARGET


def test_plan_endpoint_serves_the_thresholds_the_page_quotes(client):
    """The page words its empty states from these, so they must be the real ones."""
    thresholds = client.get("/api/plan").json()["thresholds"]

    assert thresholds == {
        "weak_score": mastery.WEAK_SCORE,
        "weak_min_problems": mastery.WEAK_MIN_PROBLEMS,
        "stale_days": weekly_analyze.STALE_DAYS,
    }


def test_plan_endpoint_lists_approach_practice_as_upcoming_until_it_is_due(client, monkeypatch):
    """Solved off-pattern today: owed, but not for three days. It is listed with its date
    and kept out of today's items, so the solve just logged does not come straight back."""
    enriched(monkeypatch, main_patterns=["prefix-sum"], intended_pattern="dp-1d")
    client.post("/api/log", json={"number": 1, "outcome": "clean", "code": CODE})
    today = date.today()

    plan = client.get("/api/plan").json()

    assert plan["topics"]["corrections_due"] == []
    assert plan["topics"]["corrections_upcoming"] == [
        {
            "number": 1,
            "title": "Two Sum",
            "accepted": ["dp-1d", "two-pointers"],
            "latest_attempt": today.isoformat(),
            "due": (today + timedelta(days=3)).isoformat(),
            "reason": "wrong-approach",
        }
    ]
    assert 1 not in [i["number"] for i in plan["items"]]


def test_plan_endpoint_puts_approach_practice_on_the_list_once_it_is_due(client, monkeypatch):
    enriched(monkeypatch, main_patterns=["prefix-sum"], intended_pattern="dp-1d")
    conn = db.connect()
    logged = service.log_solve(conn, 1, "clean", CODE, today=date.today() - timedelta(days=3))
    service.tag_solution_now(conn, logged.solution_id, service.get_problem(conn, 1), CODE)
    conn.close()

    plan = client.get("/api/plan").json()

    assert [c["number"] for c in plan["topics"]["corrections_due"]] == [1]
    assert plan["items"][0] == {
        "number": 1,
        "slug": "two-sum",
        "title": "Two Sum",
        "difficulty": "Easy",
        "reasons": [
            {"kind": "re-solve", "text": "practice an accepted approach: dp-1d or two-pointers"}
        ],
    }


def test_solutions_endpoints_list_and_serve_stored_code(client, monkeypatch):
    enriched(monkeypatch)
    client.post("/api/log", json={"number": 1, "outcome": "failed", "code": "first try\n"})
    client.post("/api/log", json={"number": 1, "outcome": "clean", "code": CODE})

    listed = client.get("/api/solutions").json()["problems"]
    assert len(listed) == 1
    assert listed[0]["solves"] == 2
    assert listed[0]["last_outcome"] == "clean"

    history = client.get("/api/solutions/1").json()
    assert [s["outcome"] for s in history["solves"]] == ["clean", "failed"]
    assert history["solves"][0]["code"] == CODE.strip()
    assert history["solves"][0]["main_patterns"] == ["hashmap"]


def test_solutions_endpoint_searches_and_counts_everything(client, monkeypatch):
    enriched(monkeypatch)
    client.post("/api/log", json={"number": 1, "outcome": "clean", "code": CODE})
    client.post("/api/log", json={"number": 15, "outcome": "clean", "code": CODE})

    default = client.get("/api/solutions").json()
    assert [p["number"] for p in default["problems"]] == [15, 1]

    found = client.get("/api/solutions", params={"q": "two"}).json()
    assert [p["number"] for p in found["problems"]] == [1]
    assert found["query"] == "two"
    assert (found["total_problems"], found["total_solves"]) == (2, 2)


def test_review_endpoint_stores_and_then_serves_for_free(client, monkeypatch):
    enriched(monkeypatch)
    logged = client.post("/api/log", json={"number": 1, "outcome": "failed", "code": CODE}).json()
    solution_id = client.get("/api/solutions/1").json()["solves"][0]["id"]
    assert logged["number"] == 1

    calls = []

    def counted(prompt, output_format, **kw):
        calls.append(prompt)
        return FEEDBACK

    monkeypatch.setattr("coach.llm.parse", counted)

    first = client.post("/api/solutions/1/review", json={"solution_id": solution_id}).json()
    assert first["status"] == "ok"
    assert first["cached"] is False
    assert first["review"]["verdict"] == "needs-work"
    assert first["review"]["strengths"] == ["Uses a dict for O(1) lookups."]
    assert first["review"]["issues"][0]["category"] == "bug"

    second = client.post("/api/solutions/1/review", json={"solution_id": solution_id}).json()
    assert second["cached"] is True
    assert len(calls) == 1

    # and it rides along on the history endpoint with no call at all
    history = client.get("/api/solutions/1").json()
    assert history["solves"][0]["review"]["verdict"] == "needs-work"
    assert len(calls) == 1


def test_review_endpoint_refresh_replaces_the_stored_review(client, monkeypatch):
    """The Re-run button: a stored review is replaced only when asked, at the cost of a call."""
    enriched(monkeypatch)
    client.post("/api/log", json={"number": 1, "outcome": "failed", "code": CODE})
    solution_id = client.get("/api/solutions/1").json()["solves"][0]["id"]

    answers = [FEEDBACK, FEEDBACK.model_copy(update={"verdict": "optimal", "issues": []})]
    calls = []

    def counted(prompt, output_format, **kw):
        calls.append(prompt)
        return answers[len(calls) - 1]

    monkeypatch.setattr("coach.llm.parse", counted)
    client.post("/api/solutions/1/review", json={"solution_id": solution_id})

    again = client.post(
        "/api/solutions/1/review", json={"solution_id": solution_id, "refresh": True}
    ).json()

    assert len(calls) == 2
    assert again["cached"] is False
    assert again["review"]["verdict"] == "optimal"
    # replaced in the store, not just in this response
    assert client.get("/api/solutions/1").json()["solves"][0]["review"]["verdict"] == "optimal"


def test_review_endpoint_reports_what_the_review_did_to_the_schedule(client, monkeypatch):
    """A clean solve whose review reports a bug is due three days after it was solved,
    and serving that stored review again reports no second effect."""
    enriched(monkeypatch)
    today = date.today()
    logged = client.post("/api/log", json={"number": 1, "outcome": "clean", "code": CODE}).json()
    solution_id = client.get("/api/solutions/1").json()["solves"][0]["id"]
    monkeypatch.setattr("coach.llm.parse", lambda prompt, output_format, **kw: FEEDBACK)

    first = client.post("/api/solutions/1/review", json={"solution_id": solution_id}).json()
    again = client.post("/api/solutions/1/review", json={"solution_id": solution_id}).json()

    assert first["effect"] == {
        "finding": "bug",
        "attempt_date": today.isoformat(),
        "latest_attempt_date": today.isoformat(),
        "next_due_before": logged["practice"]["review_due"],
        "next_due": (today + timedelta(days=3)).isoformat(),
        "rescheduled": True,
    }
    assert again["cached"] is True
    assert again["effect"] is None


def test_log_endpoint_reports_the_review_and_approach_practice_apart(client, monkeypatch):
    """Judged after enrichment, so the new tags count: a wrong-approach solve owes approach
    practice in three days, ahead of its first SM-2 review a week out."""
    enriched(monkeypatch, main_patterns=["prefix-sum"], intended_pattern="dp-1d")
    today = date.today()

    body = client.post("/api/log", json={"number": 1, "outcome": "clean", "code": CODE}).json()

    practice_due = (today + timedelta(days=3)).isoformat()
    assert body["practice"] == {
        "review_due": (today + timedelta(days=7)).isoformat(),
        "correction": {
            "number": 1,
            "title": "Two Sum",
            "accepted": ["dp-1d", "two-pointers"],
            "latest_attempt": today.isoformat(),
            "due": practice_due,
            "reason": "wrong-approach",
        },
        "next_practice": practice_due,
        "completed": False,
    }


def log_off_pattern_days_ago(monkeypatch, days):
    """A wrong-approach Two Sum solve, logged and tagged `days` ago."""
    enriched(monkeypatch, main_patterns=["prefix-sum"], intended_pattern="dp-1d")
    conn = db.connect()
    logged = service.log_solve(conn, 1, "clean", CODE, today=date.today() - timedelta(days=days))
    service.tag_solution_now(conn, logged.solution_id, service.get_problem(conn, 1), CODE)
    conn.close()


def test_log_endpoint_keeps_approach_practice_owed_after_a_failed_accepted_solve(
    client, monkeypatch
):
    log_off_pattern_days_ago(monkeypatch, 3)
    enriched(monkeypatch, main_patterns=["dp-1d"], intended_pattern="dp-1d")

    body = client.post("/api/log", json={"number": 1, "outcome": "failed", "code": CODE}).json()

    correction = body["practice"]["correction"]
    assert (correction["reason"], correction["due"]) == (
        "failed",
        (date.today() + timedelta(days=3)).isoformat(),
    )
    assert body["practice"]["completed"] is False


def test_log_endpoint_says_when_a_solve_completes_approach_practice(client, monkeypatch):
    log_off_pattern_days_ago(monkeypatch, 3)
    enriched(monkeypatch, main_patterns=["dp-1d"], intended_pattern="dp-1d")

    body = client.post("/api/log", json={"number": 1, "outcome": "clean", "code": CODE}).json()

    assert (body["practice"]["correction"], body["practice"]["completed"]) == (None, True)
    assert body["practice"]["next_practice"] == body["practice"]["review_due"]


def test_log_endpoint_says_when_a_solve_did_not_count_as_a_review(client, monkeypatch):
    """Two days after the first solve its review is still five days off, so a clean solve
    leaves it there - and says so, or the unmoved date would read as a bug."""
    log_off_pattern_days_ago(monkeypatch, 2)
    enriched(monkeypatch, main_patterns=["dp-1d"], intended_pattern="dp-1d")

    body = client.post("/api/log", json={"number": 1, "outcome": "clean", "code": CODE}).json()

    assert body["counted_as_review"] is False
    assert body["practice"]["review_due"] == (date.today() + timedelta(days=5)).isoformat()


def test_solution_history_endpoint_carries_the_same_practice_dates(client, monkeypatch):
    enriched(monkeypatch, main_patterns=["prefix-sum"], intended_pattern="dp-1d")
    logged = client.post("/api/log", json={"number": 1, "outcome": "clean", "code": CODE}).json()

    assert client.get("/api/solutions/1").json()["practice"] == logged["practice"]
    assert client.get("/api/solutions/15").json()["practice"] == {
        "review_due": None,
        "correction": None,
        "next_practice": None,
        "completed": False,
    }


def test_plan_endpoint_says_why_a_reviewed_problem_came_back(client, monkeypatch):
    """Solved five days ago, reviewed today: the bug's lapse fell due two days ago."""
    conn = db.connect()
    service.log_solve(conn, 1, "clean", CODE, today=date.today() - timedelta(days=5))
    conn.close()
    solution_id = client.get("/api/solutions/1").json()["solves"][0]["id"]
    monkeypatch.setattr("coach.llm.parse", lambda prompt, output_format, **kw: FEEDBACK)
    client.post("/api/solutions/1/review", json={"solution_id": solution_id})

    plan = client.get("/api/plan").json()

    assert [(i["number"], i["reasons"]) for i in plan["items"] if i["number"] == 1] == [
        (1, [{"kind": "review", "text": "re-solve: review reported a bug"}])
    ]
    assert plan["due_count"] == 1


def test_review_endpoint_degrades_without_an_api_key(client):
    """No key must not be an error - the solve still stands, just unreviewed."""
    client.post("/api/log", json={"number": 1, "outcome": "clean", "code": CODE})
    solution_id = client.get("/api/solutions/1").json()["solves"][0]["id"]

    body = client.post("/api/solutions/1/review", json={"solution_id": solution_id}).json()

    assert body["status"] == "skipped"
    assert body["review"] is None
    assert "ANTHROPIC_API_KEY" in body["reason"]


def test_review_endpoint_rejects_unknown_problem_and_solution(client, monkeypatch):
    enriched(monkeypatch)
    client.post("/api/log", json={"number": 1, "outcome": "clean", "code": CODE})

    assert client.post("/api/solutions/99999/review", json={"solution_id": 1}).status_code == 404
    # a real solution id, but not one belonging to this problem
    assert client.post("/api/solutions/15/review", json={"solution_id": 1}).status_code == 404


def test_solutions_endpoint_rejects_an_unknown_problem(client):
    res = client.get("/api/solutions/99999")
    assert res.status_code == 404
    assert "not in the catalog" in res.json()["detail"]


def test_endpoints_survive_parallel_requests(client, monkeypatch):
    """The browser loads /api/stats and /api/patterns at once. Each request must
    open its own connection *inside* the endpoint: a sync FastAPI dependency
    runs as a separate threadpool task, and SQLite refuses a connection used
    from a thread other than the one that created it."""
    enriched(monkeypatch)
    client.post("/api/log", json={"number": 1, "outcome": "clean", "code": CODE})

    paths = ["/api/stats", "/api/patterns", "/api/plan"] * 6
    with ThreadPoolExecutor(max_workers=8) as pool:
        codes = [r.status_code for r in pool.map(client.get, paths)]

    assert codes == [200] * len(paths)


def test_weekly_endpoint_is_empty_on_a_fresh_database(client):
    """No stored run to be missing any more - an empty week is a real answer."""
    week = client.get("/api/weekly").json()

    assert week["attempts"] == []
    assert week["patterns"] == []
    assert week["distinct_problems"] == 0
    assert week["start"] <= week["end"]


def test_weekly_endpoint_recomputes_from_the_logged_solves(client, monkeypatch):
    """Live, not frozen: logging a solve changes this endpoint's answer, and
    opening it never calls the API - the enrichment mock is for the log call."""
    enriched(monkeypatch)
    client.post("/api/log", json={"number": 1, "outcome": "struggled", "code": CODE})

    week = client.get("/api/weekly").json()

    assert [a["number"] for a in week["attempts"]] == [1]
    assert week["attempts"][0]["outcome"] == "struggled"
    assert week["attempts"][0]["main_patterns"] == ["hashmap"]
    assert week["distinct_problems"] == 1
    assert week["patterns"] == [
        {
            "pattern": "hashmap",
            "attempts_week": 1,
            "attempts_total": 1,
            "solved_total": 1,
            "score": 3.0,
            "score_before": None,
            "delta": None,
            # One problem is below WEAK_MIN_PROBLEMS, so nothing is claimed yet.
            "standing": "too-early",
        }
    ]


def test_plan_and_weekly_endpoints_never_call_the_llm(client, monkeypatch):
    """Opening a page must stay free. The daily list once also generated the week's
    report on its first run of a week - the one read that ever cost money."""
    client.post("/api/log", json={"number": 1, "outcome": "clean", "code": CODE})

    def explode(*args, **kwargs):
        raise AssertionError("a read endpoint called the API")

    monkeypatch.setattr("coach.llm.parse", explode)

    assert client.get("/api/plan").status_code == 200
    assert client.get("/api/weekly").status_code == 200
    assert client.get("/api/solutions/1").status_code == 200


def test_weekly_endpoint_serves_the_thresholds_the_page_quotes(client):
    week = client.get("/api/weekly").json()

    assert week["thresholds"]["weak_score"] == mastery.WEAK_SCORE
    assert week["thresholds"]["weak_min_problems"] == mastery.WEAK_MIN_PROBLEMS


def test_pages_are_served(client):
    for path in ("/", "/plan", "/solutions", "/weekly"):
        res = client.get(path)
        assert res.status_code == 200
        assert "text/html" in res.headers["content-type"]
    assert client.get("/static/home.js").status_code == 200
    assert client.get("/static/solutions.js").status_code == 200
    assert client.get("/static/weekly.js").status_code == 200


def test_pages_and_scripts_are_revalidated(client):
    """A page and its script are one unit, and a stale script breaks the page in
    silence: it looks up elements the new markup no longer has, gets null, and the
    error path reaches for a missing element too, so the page sits on its loading
    text with nothing rendered and no message. Revalidating both prevents the pair
    from ever being mismatched; the 304 it usually gets back costs nothing here.
    """
    for path in ("/", "/plan", "/solutions", "/weekly",
                 "/static/weekly.js", "/static/plan.js", "/static/style.css"):
        assert client.get(path).headers["cache-control"] == "no-cache", path
