import json

import numpy as np
import pytest
from conftest import CODE, seed_db, tag_solution
from typer.testing import CliRunner

from coach import db, embed, enrich, llm, service
from coach.cli import app

runner = CliRunner()


def setup_env(tmp_path, monkeypatch):
    """Seed the scratch database and let go of it - every CLI command opens its own."""
    seed_db(tmp_path, monkeypatch).close()


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


def fake_encode(texts):
    vector = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    return np.tile(vector, (len(texts), 1))


def test_enrich_backfills_tags_and_embeddings(tmp_path, monkeypatch):
    conn = seed_db(tmp_path, monkeypatch)
    service.log_solve(conn, 1, "clean", CODE)  # no key -> logged without enrichment
    conn.close()

    monkeypatch.setattr("coach.llm.parse", lambda prompt, output_format, **kw: ENRICHMENT)
    monkeypatch.setattr("coach.embed.encode", fake_encode)
    result = runner.invoke(app, ["enrich"])
    assert result.exit_code == 0, result.output
    assert "Enriched 1/1" in result.output
    assert "Embedded 1" in result.output

    conn = db.connect()
    assert conn.execute("SELECT COUNT(*) FROM enrichments").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0] == 1


def log_unenriched(tmp_path, monkeypatch, solves=1):
    """Log Two Sum `solves` times with no API key, so each waits for `coach enrich`."""
    conn = seed_db(tmp_path, monkeypatch)
    for _ in range(solves):
        service.log_solve(conn, 1, "clean", CODE)
    return conn


def answer(monkeypatch, **overrides):
    e = ENRICHMENT.model_copy(update=overrides)
    monkeypatch.setattr("coach.llm.parse", lambda prompt, output_format, **kw: e)
    monkeypatch.setattr("coach.embed.encode", fake_encode)


def answer_once(monkeypatch, **overrides):
    """The model answers one solve, then is rate limited, so the run stops partway."""
    answers = iter([ENRICHMENT.model_copy(update=overrides)])

    def parse_once(prompt, output_format, **kw):
        try:
            return next(answers)
        except StopIteration:
            raise llm.LLMUnavailable("rate limited") from None

    monkeypatch.setattr("coach.llm.parse", parse_once)


def no_embeddings(texts):
    raise embed.EmbeddingsUnavailable("sentence-transformers not installed")


def record_cards(monkeypatch) -> list[str]:
    """Encode as usual, and return the list every card sent to the encoder lands in."""
    cards = []
    monkeypatch.setattr("coach.embed.encode", lambda texts: cards.extend(texts) or fake_encode(texts))
    return cards


def count(table):
    conn = db.connect()
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


def test_enrich_judges_against_the_stored_canonical_set(tmp_path, monkeypatch):
    """The agreement the log endpoint keeps, kept here too: an answer that forgets an
    accepted approach must not mark a solve that used it."""
    conn = log_unenriched(tmp_path, monkeypatch)
    enrich.save_intended(conn, 1, "hashmap", ["two-pointers"])
    conn.commit()
    conn.close()
    answer(monkeypatch, main_patterns=["two-pointers"], intended_secondary_patterns=[])

    result = runner.invoke(app, ["enrich"])

    assert result.exit_code == 0, result.output
    assert "#1 Two Sum: two-pointers" in result.output
    assert "(canonical:" not in result.output


def test_enrich_marks_an_off_pattern_solve(tmp_path, monkeypatch):
    log_unenriched(tmp_path, monkeypatch).close()
    answer(monkeypatch, main_patterns=["prefix-sum"], intended_pattern="dp-1d")

    result = runner.invoke(app, ["enrich"])

    assert "#1 Two Sum: prefix-sum" in result.output
    assert "(canonical: dp-1d)" in result.output


def test_enrich_without_a_key_stops_and_keeps_the_solve(tmp_path, monkeypatch):
    log_unenriched(tmp_path, monkeypatch).close()

    result = runner.invoke(app, ["enrich"])

    assert result.exit_code == 0, result.output
    assert "Stopped at #1" in result.output
    assert "Enriched 0/1" in result.output
    assert count("solutions") == 1
    conn = db.connect()
    assert len(enrich.to_tag(conn)) == 1


def test_enrich_embeds_on_a_later_run_what_an_earlier_run_only_tagged(tmp_path, monkeypatch):
    log_unenriched(tmp_path, monkeypatch).close()
    answer(monkeypatch)

    monkeypatch.setattr("coach.embed.encode", no_embeddings)
    first = runner.invoke(app, ["enrich"])
    assert "Enriched 1/1" in first.output
    assert "Embeddings skipped" in first.output
    assert (count("enrichments"), count("embeddings")) == (1, 0)

    monkeypatch.setattr("coach.embed.encode", fake_encode)
    second = runner.invoke(app, ["enrich"])
    assert "Enriched 0/0" in second.output
    assert "Embedded 1" in second.output
    assert (count("enrichments"), count("embeddings")) == (1, 1)


def test_enrich_resumes_a_backfill_that_stopped_partway(tmp_path, monkeypatch):
    log_unenriched(tmp_path, monkeypatch, solves=2).close()
    answer(monkeypatch)
    answer_once(monkeypatch)
    first = runner.invoke(app, ["enrich"])
    assert "Stopped at #1: rate limited" in first.output
    assert "Enriched 1/2" in first.output
    # what the stopped run did tag is stored and embedded
    assert (count("enrichments"), count("embeddings")) == (1, 1)

    answer(monkeypatch)
    second = runner.invoke(app, ["enrich"])
    assert "Enriched 1/1" in second.output
    assert (count("enrichments"), count("embeddings")) == (2, 2)


def test_enrich_retag_re_tags_and_re_embeds_tagged_solves(tmp_path, monkeypatch):
    """A new prompt only reaches old solves if they can be tagged again: plain `enrich`
    leaves a tagged solve alone, `--retag` replaces its tags - and the stored vector,
    whose card text names the patterns, so it never describes the tags it replaced."""
    log_unenriched(tmp_path, monkeypatch).close()
    answer(monkeypatch)
    runner.invoke(app, ["enrich"])
    assert "Enriched 0/0" in runner.invoke(app, ["enrich"]).output

    answer(monkeypatch, main_patterns=["hashmap", "two-pointers"])
    cards = record_cards(monkeypatch)
    result = runner.invoke(app, ["enrich", "--retag"])

    assert result.exit_code == 0, result.output
    assert "#1 Two Sum: hashmap, two-pointers" in result.output
    assert "Enriched 1/1" in result.output
    conn = db.connect()
    stored = conn.execute("SELECT main_patterns FROM enrichments").fetchone()[0]
    assert json.loads(stored) == ["hashmap", "two-pointers"]
    assert (count("enrichments"), count("embeddings")) == (1, 1)
    assert len(cards) == 1 and "\npattern: hashmap, two-pointers\n" in cards[0]


def test_enrich_rebuilds_the_vector_a_failed_retag_discarded(tmp_path, monkeypatch):
    """A retag whose embedding fails used to keep the old vector under the new tags, and
    plain `enrich` only looked for solves with no vector, so it never noticed. The retag
    now drops the vector with the tags it described, and plain `enrich` rebuilds it from
    the stored tags without asking the model again."""
    log_unenriched(tmp_path, monkeypatch).close()
    answer(monkeypatch)
    runner.invoke(app, ["enrich"])

    answer(monkeypatch, main_patterns=["dp-1d"])
    monkeypatch.setattr("coach.embed.encode", no_embeddings)
    retag = runner.invoke(app, ["enrich", "--retag"])
    assert "Embeddings skipped" in retag.output
    assert (count("enrichments"), count("embeddings")) == (1, 0)

    cards = record_cards(monkeypatch)
    retry = runner.invoke(app, ["enrich"])

    assert "Enriched 0/0" in retry.output  # nothing sent to the model
    assert "Embedded 1" in retry.output
    assert len(cards) == 1 and "\npattern: dp-1d\n" in cards[0]


def test_enrich_retag_stopped_partway_re_embeds_only_what_it_re_tagged(tmp_path, monkeypatch):
    """A solve the retag never reached keeps its tags, so its vector still describes them."""
    log_unenriched(tmp_path, monkeypatch, solves=2).close()
    answer(monkeypatch)
    runner.invoke(app, ["enrich"])

    answer_once(monkeypatch, main_patterns=["dp-1d"])
    cards = record_cards(monkeypatch)
    result = runner.invoke(app, ["enrich", "--retag"])

    assert "Enriched 1/2" in result.output
    assert len(cards) == 1 and "\npattern: dp-1d\n" in cards[0]
    assert count("embeddings") == 2


def test_enrich_no_longer_offers_missing(tmp_path, monkeypatch):
    """--missing was declared and never read; asking for it now fails loudly."""
    setup_env(tmp_path, monkeypatch)

    assert runner.invoke(app, ["enrich", "--missing"]).exit_code != 0


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
    store_embedded_solve(conn, 1, [1.0, 0.0])
    store_embedded_solve(conn, 15, [0.8, 0.6])
    conn.commit()
    conn.close()

    result = runner.invoke(app, ["similar", "1"])
    assert result.exit_code == 0, result.output
    assert "#15 3Sum" in result.output
    assert "#1 Two Sum" not in result.output  # the query problem itself is excluded


def store_embedded_solve(conn, number, vector, pattern="hashmap"):
    """A tagged, embedded solve stored directly - `similar` by number needs no model to read it."""
    solution_id = conn.execute(
        "INSERT INTO solutions (problem_number, code, created_at) VALUES (?, 'c', '2026-01-01')",
        (number,),
    ).lastrowid
    tag_solution(conn, solution_id, pattern)
    embed.store(conn, solution_id, np.array(vector, dtype=np.float32))


def test_similar_by_number_searches_through_every_solve_of_the_problem(tmp_path, monkeypatch):
    """A problem solved two ways is similar to the relatives of both approaches: querying
    with its latest solve alone scored a relative of the earlier approach as unrelated."""
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
            },
            {
                "number": 217,
                "slug": "contains-duplicate",
                "title": "Contains Duplicate",
                "difficulty": "Easy",
                "official_tags": "[]",
                "paid_only": 0,
            },
        ],
    )
    store_embedded_solve(conn, 1, [1.0, 0.0], "hashmap")
    store_embedded_solve(conn, 1, [0.0, 1.0], "two-pointers")  # the latest solve
    store_embedded_solve(conn, 217, [1.0, 0.0], "hashmap")
    store_embedded_solve(conn, 15, [0.0, 1.0], "two-pointers")
    conn.commit()
    conn.close()

    result = runner.invoke(app, ["similar", "1"])

    assert result.exit_code == 0, result.output
    assert "#15 3Sum [Medium]  1.00" in result.output
    assert "#217 Contains Duplicate [Easy]  1.00" in result.output


@pytest.mark.parametrize(
    "days",
    [("2026-09-01",) * 3, ("2026-09-01", "2026-09-02", "2026-09-03")],
    ids=["same-day", "before-due"],
)
def test_init_reschedules_problems_from_their_attempts(tmp_path, monkeypatch, days):
    """A schedule stored while every solve still counted - three in one day, or three days
    running before the first review was due - stays stretched until that problem is logged
    again, so `coach init` re-derives each one from its attempts."""
    conn = seed_db(tmp_path, monkeypatch)
    for day in days:
        conn.execute(
            "INSERT INTO attempts (problem_number, date, outcome) VALUES (1, ?, 'clean')", (day,)
        )
    # what counting every solve as a review stored after those three
    conn.execute(
        """
        INSERT INTO review_state (problem_number, ease, interval_days, next_due, reps, lapses)
        VALUES (1, 2.8, 39.2, '2026-10-10', 3, 0)
        """
    )
    conn.commit()
    conn.close()
    two_sum = {
        "number": 1,
        "slug": "two-sum",
        "title": "Two Sum",
        "difficulty": "Easy",
        "tags": ["array"],
        "paid_only": False,
    }
    monkeypatch.setattr("coach.catalog.load", lambda: [two_sum])

    result = runner.invoke(app, ["init"])

    assert result.exit_code == 0, result.output
    assert "Rescheduled 1 problem(s)" in result.output
    conn = db.connect()
    state = conn.execute("SELECT reps, interval_days, next_due FROM review_state").fetchone()
    assert tuple(state) == (1, 7.0, "2026-09-08")
