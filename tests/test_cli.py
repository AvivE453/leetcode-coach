import numpy as np
from conftest import CODE, seed_db
from typer.testing import CliRunner

from coach import db, embed, enrich, service
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
