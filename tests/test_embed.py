import numpy as np
from conftest import tag_solution

from coach import db, embed


def unit(x, y):
    v = np.array([x, y], dtype=np.float32)
    return v / np.linalg.norm(v)


def make_db(tmp_path):
    conn = db.connect(tmp_path / "test.db")
    db.init_schema(conn)
    return conn


def add_embedded_solution(conn, number, vector, patterns=("test-pattern",)):
    if not conn.execute("SELECT 1 FROM problems WHERE number = ?", (number,)).fetchone():
        conn.execute(
            "INSERT INTO problems (number, slug, title, difficulty) VALUES (?, ?, ?, 'Easy')",
            (number, f"p{number}", f"Problem {number}"),
        )
    solution_id = conn.execute(
        "INSERT INTO solutions (problem_number, code, created_at) VALUES (?, 'c', '2026-01-01')",
        (number,),
    ).lastrowid
    tag_solution(conn, solution_id, *patterns)
    embed.store(conn, solution_id, vector)


def test_card_text_contains_all_parts():
    card = embed.card_text("Two Sum", ["hashmap"], "complements", "def f(): ...")
    # One main pattern reads exactly as the single-pattern card did, so vectors
    # embedded before a solve could have several still describe the same text.
    assert card == "Two Sum\npattern: hashmap\ntrick: complements\n\ndef f(): ..."


def test_card_text_lists_every_main_pattern():
    card = embed.card_text("Coin Change II", ["dp-knapsack", "dfs"], "count per coin", "code")
    assert "\npattern: dp-knapsack, dfs\n" in card


def test_search_ranks_by_cosine(tmp_path):
    conn = make_db(tmp_path)
    add_embedded_solution(conn, 1, unit(1, 0))
    add_embedded_solution(conn, 2, unit(0.9, 0.4))
    add_embedded_solution(conn, 3, unit(0, 1))

    results = embed.search(conn, unit(1, 0), top_k=2)
    assert [number for number, _ in results] == [1, 2]
    assert results[0][1] > results[1][1]


def test_search_excludes_query_problem(tmp_path):
    conn = make_db(tmp_path)
    add_embedded_solution(conn, 1, unit(1, 0))
    add_embedded_solution(conn, 2, unit(0.9, 0.4))

    results = embed.search(conn, unit(1, 0), top_k=5, exclude_problem=1)
    assert [number for number, _ in results] == [2]


def test_search_dedupes_multiple_solutions_per_problem(tmp_path):
    conn = make_db(tmp_path)
    add_embedded_solution(conn, 1, unit(1, 0))
    add_embedded_solution(conn, 1, unit(0, 1))
    add_embedded_solution(conn, 2, unit(0.5, 0.5))

    results = embed.search(conn, unit(1, 0), top_k=5)
    assert [number for number, _ in results] == [1, 2]
    assert results[0][1] == 1.0  # best of problem 1's two vectors, not the average


def test_search_filters_by_pattern(tmp_path):
    conn = make_db(tmp_path)
    add_embedded_solution(conn, 1, unit(1, 0), patterns=("hashmap",))
    add_embedded_solution(conn, 2, unit(0.9, 0.4), patterns=("two-pointers",))

    results = embed.search(conn, unit(1, 0), top_k=5, patterns=["hashmap"])
    assert [number for number, _ in results] == [1]


def test_search_with_pattern_finds_nothing_outside_it(tmp_path):
    conn = make_db(tmp_path)
    add_embedded_solution(conn, 1, unit(1, 0), patterns=("hashmap",))

    results = embed.search(conn, unit(1, 0), top_k=5, exclude_problem=1, patterns=["hashmap"])
    assert results == []


def test_search_keeps_a_solution_sharing_any_main_pattern(tmp_path):
    """Main patterns are equal, so sharing any one of them is enough to be compared."""
    conn = make_db(tmp_path)
    add_embedded_solution(conn, 1, unit(1, 0), patterns=("dfs", "dp-knapsack"))
    add_embedded_solution(conn, 2, unit(0.9, 0.4), patterns=("tree",))

    results = embed.search(conn, unit(1, 0), top_k=5, patterns=["dp-knapsack", "math"])
    assert [number for number, _ in results] == [1]
