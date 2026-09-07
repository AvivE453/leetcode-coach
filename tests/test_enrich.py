import json

from coach import db, enrich

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
    row = conn.execute("SELECT * FROM problems WHERE number = 1").fetchone()
    assert row["intended_pattern"] == "dp-1d"
    assert json.loads(row["intended_secondary_patterns"]) == []


def test_save_intended_stores_alternates_without_repeating_the_central_one(tmp_path):
    conn = make_db(tmp_path)
    enrich.save_intended(conn, 1, "dp-1d", ["greedy", "dp-1d", "greedy"])
    row = conn.execute("SELECT * FROM problems WHERE number = 1").fetchone()
    assert row["intended_pattern"] == "dp-1d"
    # the central pattern and the duplicate are both dropped: the two columns are
    # read back as one set, so a repeat would surface as a repeated note
    assert json.loads(row["intended_secondary_patterns"]) == ["greedy"]


def test_save_intended_accumulates_alternates_across_enrichments(tmp_path):
    """A re-enrichment must not narrow the canonical set.

    Every re-solve enriches again, and the model does not always name the same
    alternates twice. Replacing the column let the second answer drop an approach
    the first had accepted.
    """
    conn = make_db(tmp_path)
    enrich.save_intended(conn, 1, "greedy", ["dp-1d"])
    enrich.save_intended(conn, 1, "dp-1d", [])

    row = conn.execute("SELECT * FROM problems WHERE number = 1").fetchone()
    # the newest answer owns the central slot; the previous central one is demoted,
    # not discarded, so both approaches stay canonical
    assert row["intended_pattern"] == "dp-1d"
    assert json.loads(row["intended_secondary_patterns"]) == ["greedy"]


def test_re_enriching_does_not_re_flag_a_cleared_solve(tmp_path):
    """The bug this guards: a solved-correctly problem reappearing as off-pattern.

    #121 is solved with greedy while greedy is canonical. A later enrichment names
    only dp-1d. Before, that re-flagged the greedy solve and earned it a forced
    re-solve slot in `coach today`.
    """
    conn = make_db(tmp_path)
    enrich.save_intended(conn, 1, "greedy", ["dp-1d"])
    enrich_solution_row(conn, "greedy")
    assert enrich.off_pattern_problems(conn) == []

    enrich.save_intended(conn, 1, "dp-1d", [])

    assert [r["number"] for r in enrich.off_pattern_problems(conn)] == []


CANONICAL = ("hashmap", ["two-pointers"])


def test_off_pattern_accepts_any_canonical_approach():
    intended, alternates = CANONICAL
    # the central approach, and an alternate one, are both on-pattern
    assert enrich.off_pattern("hashmap", [], intended, alternates) is False
    assert enrich.off_pattern("two-pointers", [], intended, alternates) is False
    # so is a solve that reached one of them as a secondary tag
    assert enrich.off_pattern("math", ["two-pointers"], intended, alternates) is False
    # nothing canonical anywhere -> the sharp signal fires
    assert enrich.off_pattern("math", ["stack"], intended, alternates) is True
    # a problem that was never enriched has no canonical set to be outside of
    assert enrich.off_pattern("math", [], None, []) is False


def test_unused_canonical_lists_what_is_left_central_first():
    intended, alternates = CANONICAL
    assert enrich.unused_canonical("hashmap", [], intended, alternates) == ["two-pointers"]
    assert enrich.unused_canonical("two-pointers", [], intended, alternates) == ["hashmap"]
    # an off-pattern solve gets the whole canonical set, central approach first
    assert enrich.unused_canonical("math", [], intended, alternates) == ["hashmap", "two-pointers"]
    # nothing left to suggest once every canonical approach has been practised
    assert enrich.unused_canonical("hashmap", ["two-pointers"], intended, alternates) == []
    assert enrich.unused_canonical("math", [], None, []) == []


def enrich_solution_row(conn, pattern, secondary=()):
    solution_id = add_solution(conn)
    conn.execute(
        "INSERT INTO enrichments (solution_id, pattern, secondary_patterns) VALUES (?, ?, ?)",
        (solution_id, pattern, json.dumps(list(secondary))),
    )
    conn.commit()


def test_off_pattern_problems_clears_on_any_canonical_approach(tmp_path):
    conn = make_db(tmp_path)
    enrich.save_intended(conn, 1, "hashmap", ["two-pointers"])
    enrich_solution_row(conn, "math")
    assert [r["number"] for r in enrich.off_pattern_problems(conn)] == [1]

    # a later solve using the *alternate* canonical approach clears the problem
    enrich_solution_row(conn, "two-pointers")
    assert enrich.off_pattern_problems(conn) == []


def test_off_pattern_problems_matches_an_alternate_in_solution_secondaries(tmp_path):
    conn = make_db(tmp_path)
    enrich.save_intended(conn, 1, "hashmap", ["two-pointers"])
    enrich_solution_row(conn, "math", secondary=["two-pointers"])

    assert enrich.off_pattern_problems(conn) == []


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
