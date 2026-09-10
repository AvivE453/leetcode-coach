from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest
from conftest import CODE, seed_db
from fastapi.testclient import TestClient

from coach import config, db, enrich, mastery, review
from coach.web.app import app
from coach.weekly import analyze as weekly_analyze

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
    assert body["enrichment"]["status"] == "ok"
    assert body["enrichment"]["pattern"] == "hashmap"
    assert body["enrichment"]["off_pattern"] is False

    conn = db.connect()
    assert conn.execute("SELECT outcome FROM attempts").fetchone()["outcome"] == "struggled"
    assert conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0] == 1
    assert client.get("/api/stats").json()["solved"] == 1


def test_log_endpoint_flags_off_pattern_solves(client, monkeypatch):
    enriched(monkeypatch, pattern="prefix-sum", intended_pattern="dp-1d")

    body = client.post("/api/log", json={"number": 1, "outcome": "clean", "code": CODE}).json()

    assert body["enrichment"]["off_pattern"] is True
    assert body["enrichment"]["intended_pattern"] == "dp-1d"
    assert body["enrichment"]["intended_secondary_patterns"] == ["two-pointers"]
    assert body["enrichment"]["also_solvable_with"] == ["dp-1d", "two-pointers"]


def test_log_endpoint_accepts_a_canonical_alternate_approach(client, monkeypatch):
    """An alternate canonical route is not off-pattern, but the unused central
    approach is still worth mentioning."""
    enriched(monkeypatch, pattern="two-pointers", intended_pattern="hashmap")

    body = client.post("/api/log", json={"number": 1, "outcome": "clean", "code": CODE}).json()

    assert body["enrichment"]["off_pattern"] is False
    assert body["enrichment"]["also_solvable_with"] == ["hashmap"]


def test_solution_history_endpoint_carries_the_canonical_note(client, monkeypatch):
    enriched(monkeypatch)
    client.post("/api/log", json={"number": 1, "outcome": "clean", "code": CODE})

    body = client.get("/api/solutions/1").json()

    assert body["intended_secondary_patterns"] == ["two-pointers"]
    assert body["solves"][0]["also_solvable_with"] == ["two-pointers"]
    assert body["solves"][0]["secondary_patterns"] == []


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

    assert body["pattern_standing"] == {
        "pattern": "hashmap",
        "attempts": 1,
        "struggle_rate": 1.0,
        "score": 1.0,
        "weak": False,
        "enough_data": False,
    }


def test_log_endpoint_reports_a_weak_pattern(client, monkeypatch):
    enriched(monkeypatch)
    for number in (1, 15, 1, 15):
        client.post("/api/log", json={"number": number, "outcome": "failed", "code": CODE})

    body = client.post("/api/log", json={"number": 1, "outcome": "failed", "code": CODE}).json()

    assert body["pattern_standing"] == {
        "pattern": "hashmap",
        "attempts": 5,
        "struggle_rate": 1.0,
        "score": 1.0,
        "weak": True,
        "enough_data": True,
    }


def test_log_endpoint_has_no_standing_without_enrichment(client):
    body = client.post("/api/log", json={"number": 1, "outcome": "clean", "code": CODE}).json()

    assert body["enrichment"]["status"] == "skipped"
    assert body["pattern_standing"] is None


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

    # two attempts on one problem is still one solved unit
    assert client.get("/api/patterns").json() == {"patterns": [{"pattern": "hashmap", "solved": 1}]}


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

    numbers = [i["number"] for i in plan["items"]]
    assert numbers == [1, 15]  # the due review outranks curriculum progression
    assert plan["items"][0]["kind"] == "review"
    assert plan["items"][1]["kind"] == "curriculum"
    assert plan["topics"] == {"weak": [], "stale": [], "off_pattern": []}
    assert not (tmp_path / "reports").exists()


def test_plan_endpoint_labels_a_weak_pattern_pick(client, monkeypatch):
    """The one chip class no test reached: a pick made to practice a weak pattern.

    It is the branch furthest from the endpoint - a pattern has to go weak, and an
    unsolved problem has to carry the matching official tag - which is exactly why
    it went uncovered while the kind was recovered by parsing the reason sentence.
    """
    enriched(monkeypatch, pattern="two-pointers")
    for _ in range(mastery.WEAK_MIN_ATTEMPTS):
        client.post("/api/log", json={"number": 1, "outcome": "failed", "code": CODE})

    plan = client.get("/api/plan").json()

    assert plan["topics"]["weak"] == ["two-pointers"]
    # #15 is unsolved, on the curriculum, and officially tagged two-pointers.
    assert [(i["number"], i["kind"]) for i in plan["items"]] == [(15, "weak-pattern")]
    assert plan["items"][0]["reason"] == "weak pattern: two-pointers"


def test_plan_endpoint_only_counts_reviews_due_today(client, monkeypatch):
    """The page is /plan's "Today", not the old weekly view: a review owed in
    three days must not appear, even though `coach weekly` would show it."""
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
        "weak_min_attempts": mastery.WEAK_MIN_ATTEMPTS,
        "stale_days": weekly_analyze.STALE_DAYS,
    }


def test_plan_endpoint_surfaces_off_pattern_topics(client, monkeypatch):
    enriched(monkeypatch, pattern="prefix-sum", intended_pattern="dp-1d")
    client.post("/api/log", json={"number": 1, "outcome": "clean", "code": CODE})

    plan = client.get("/api/plan").json()

    assert plan["topics"]["off_pattern"] == [
        {"number": 1, "title": "Two Sum", "intended_pattern": "dp-1d"}
    ]
    assert plan["items"][0]["kind"] in {"review", "re-solve"}


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
    assert history["solves"][0]["pattern"] == "hashmap"


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
    assert week["distinct_problems"] == 1
    assert week["patterns"] == [
        {
            "pattern": "hashmap",
            "attempts_week": 1,
            "attempts_total": 1,
            "score": 3.0,
            "score_before": None,
            "delta": None,
            # One attempt is below WEAK_MIN_ATTEMPTS, so nothing is claimed yet.
            "standing": "too-early",
        }
    ]


def test_weekly_endpoint_serves_the_thresholds_the_page_quotes(client):
    week = client.get("/api/weekly").json()

    assert week["thresholds"]["weak_score"] == mastery.WEAK_SCORE
    assert week["thresholds"]["weak_min_attempts"] == mastery.WEAK_MIN_ATTEMPTS


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
