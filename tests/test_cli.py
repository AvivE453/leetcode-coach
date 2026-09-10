import numpy as np
from conftest import CODE, seed_db
from typer.testing import CliRunner

from coach import db, embed, enrich, llm, service
from coach.cli import app

runner = CliRunner()


def setup_env(tmp_path, monkeypatch):
    """Seed the scratch database and let go of it - every CLI command opens its own."""
    seed_db(tmp_path, monkeypatch).close()


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
    answer(monkeypatch, pattern="two-pointers", intended_secondary_patterns=[])

    result = runner.invoke(app, ["enrich"])

    assert result.exit_code == 0, result.output
    assert "#1 Two Sum: two-pointers" in result.output
    assert "(canonical:" not in result.output


def test_enrich_marks_an_off_pattern_solve(tmp_path, monkeypatch):
    log_unenriched(tmp_path, monkeypatch).close()
    answer(monkeypatch, pattern="prefix-sum", intended_pattern="dp-1d")

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
    assert len(enrich.missing(conn)) == 1


def test_enrich_embeds_on_a_later_run_what_an_earlier_run_only_tagged(tmp_path, monkeypatch):
    log_unenriched(tmp_path, monkeypatch).close()
    answer(monkeypatch)

    def no_embeddings(texts):
        raise embed.EmbeddingsUnavailable("sentence-transformers not installed")

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
    answers = iter([ENRICHMENT])

    def parse_once(prompt, output_format, **kw):
        try:
            return next(answers)
        except StopIteration:
            raise llm.LLMUnavailable("rate limited") from None

    monkeypatch.setattr("coach.llm.parse", parse_once)
    first = runner.invoke(app, ["enrich"])
    assert "Stopped at #1: rate limited" in first.output
    assert "Enriched 1/2" in first.output
    # what the stopped run did tag is stored, scored and embedded
    assert (count("enrichments"), count("pattern_scores"), count("embeddings")) == (1, 1, 1)

    answer(monkeypatch)
    second = runner.invoke(app, ["enrich"])
    assert "Enriched 1/1" in second.output
    assert (count("enrichments"), count("embeddings")) == (2, 2)


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
