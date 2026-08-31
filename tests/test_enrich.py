import json

from coach import db, enrich

ENRICHMENT = enrich.Enrichment(
    pattern="hashmap",
    intended_pattern="hashmap",
    secondary_patterns=[],
    data_structures=["dict"],
    key_trick="Store complements while scanning once.",
    time_complexity="O(n)",
    space_complexity="O(n)",
)


def make_db(tmp_path):
    conn = db.connect(tmp_path / "test.db")
    db.init_schema(conn)
    conn.execute(
        "INSERT INTO problems (number, slug, title, difficulty) VALUES (1, 'two-sum', 'Two Sum', 'Easy')"
    )
    return conn


def add_solution(conn, code="code"):
    return conn.execute(
        "INSERT INTO solutions (problem_number, code, created_at) VALUES (1, ?, '2026-01-01')",
        (code,),
    ).lastrowid


def test_pattern_vocabulary_is_unique_and_kebab_case():
    assert len(enrich.PATTERNS) == 26
    assert len(set(enrich.PATTERNS)) == 26
    for pattern in enrich.PATTERNS:
        assert pattern == pattern.lower()
        assert " " not in pattern


def test_save_and_missing(tmp_path):
    conn = make_db(tmp_path)
    first = add_solution(conn)
    second = add_solution(conn)

    assert [r["solution_id"] for r in enrich.missing(conn)] == [first, second]

    enrich.save(conn, first, ENRICHMENT)
    assert [r["solution_id"] for r in enrich.missing(conn)] == [second]

    row = conn.execute("SELECT * FROM enrichments WHERE solution_id = ?", (first,)).fetchone()
    assert row["pattern"] == "hashmap"
    assert json.loads(row["data_structures"]) == ["dict"]
    assert row["prompt_version"] == enrich.PROMPT_VERSION


def test_save_intended_updates_problem(tmp_path):
    conn = make_db(tmp_path)
    enrich.save_intended(conn, 1, "dp-1d")
    row = conn.execute("SELECT intended_pattern FROM problems WHERE number = 1").fetchone()
    assert row["intended_pattern"] == "dp-1d"


def test_enrich_solution_builds_prompt_and_parses(monkeypatch):
    captured = {}

    def fake_parse(prompt, output_format, **kwargs):
        captured["prompt"] = prompt
        captured["output_format"] = output_format
        return ENRICHMENT

    monkeypatch.setattr(enrich.llm, "parse", fake_parse)
    problem = {
        "number": 1,
        "title": "Two Sum",
        "difficulty": "Easy",
        "official_tags": '["Array", "Hash Table"]',
    }
    result = enrich.enrich_solution(problem, "def twoSum(): ...")

    assert result is ENRICHMENT
    assert captured["output_format"] is enrich.Enrichment
    assert "Two Sum" in captured["prompt"]
    assert "def twoSum" in captured["prompt"]
    assert "Array, Hash Table" in captured["prompt"]
