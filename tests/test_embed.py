import numpy as np
import pytest
from conftest import tag_solution

from coach import db, embed


def unit(x, y):
    v = np.array([x, y], dtype=np.float32)
    return v / np.linalg.norm(v)


def query(*vectors):
    """search() takes its query vectors one per row."""
    return np.stack(vectors)


def make_db(tmp_path):
    conn = db.connect(tmp_path / "test.db")
    db.init_schema(conn)
    return conn


def add_embedded_solution(conn, number, vector, patterns=("test-pattern",)) -> int:
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
    return solution_id


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

    results = embed.search(conn, query(unit(1, 0)), top_k=2)
    assert [hit.number for hit in results] == [1, 2]
    assert results[0].score > results[1].score


def test_search_excludes_query_problem(tmp_path):
    conn = make_db(tmp_path)
    add_embedded_solution(conn, 1, unit(1, 0))
    add_embedded_solution(conn, 2, unit(0.9, 0.4))

    results = embed.search(conn, query(unit(1, 0)), top_k=5, exclude_problem=1)
    assert [hit.number for hit in results] == [2]


def test_search_dedupes_multiple_solutions_per_problem(tmp_path):
    conn = make_db(tmp_path)
    add_embedded_solution(conn, 1, unit(1, 0))
    add_embedded_solution(conn, 1, unit(0, 1))
    add_embedded_solution(conn, 2, unit(0.5, 0.5))

    results = embed.search(conn, query(unit(1, 0)), top_k=5)
    assert [hit.number for hit in results] == [1, 2]
    assert results[0].score == 1.0  # best of problem 1's two vectors, not the average


def test_search_names_the_solve_that_scored_best(tmp_path):
    """The hit carries the solve that matched, so it can be described by that solve's approach."""
    conn = make_db(tmp_path)
    matching = add_embedded_solution(conn, 1, unit(1, 0))
    add_embedded_solution(conn, 1, unit(0, 1))

    [hit] = embed.search(conn, query(unit(1, 0)))
    assert hit.solution_id == matching


def test_search_names_the_latest_solve_on_a_tie(tmp_path):
    """Re-solving a problem the same way embeds the same card twice; the latest is the one shown."""
    conn = make_db(tmp_path)
    add_embedded_solution(conn, 1, unit(1, 0))
    latest = add_embedded_solution(conn, 1, unit(1, 0))

    [hit] = embed.search(conn, query(unit(1, 0)))
    assert hit.solution_id == latest


def test_search_scores_each_solve_by_its_best_query(tmp_path):
    """Asking with every solve of a problem finds the relatives of each of its approaches."""
    conn = make_db(tmp_path)
    add_embedded_solution(conn, 1, unit(1, 0))
    add_embedded_solution(conn, 2, unit(0, 1))

    results = embed.search(conn, query(unit(1, 0), unit(0, 1)))
    assert sorted((hit.number, hit.score) for hit in results) == [(1, 1.0), (2, 1.0)]


def test_search_filters_by_pattern(tmp_path):
    conn = make_db(tmp_path)
    add_embedded_solution(conn, 1, unit(1, 0), patterns=("hashmap",))
    add_embedded_solution(conn, 2, unit(0.9, 0.4), patterns=("two-pointers",))

    results = embed.search(conn, query(unit(1, 0)), top_k=5, patterns=["hashmap"])
    assert [hit.number for hit in results] == [1]


def test_search_filters_patterns_solve_by_solve(tmp_path):
    """A problem solved two ways matches through the solve sharing the pattern, even when
    its other solve would have scored higher."""
    conn = make_db(tmp_path)
    dp = add_embedded_solution(conn, 1, unit(0.6, 0.8), patterns=("dp-1d",))
    add_embedded_solution(conn, 1, unit(1, 0), patterns=("greedy",))

    [hit] = embed.search(conn, query(unit(1, 0)), patterns=["dp-1d"])
    assert hit.solution_id == dp
    assert hit.score == pytest.approx(0.6)


def test_search_with_pattern_finds_nothing_outside_it(tmp_path):
    conn = make_db(tmp_path)
    add_embedded_solution(conn, 1, unit(1, 0), patterns=("hashmap",))

    results = embed.search(conn, query(unit(1, 0)), top_k=5, exclude_problem=1, patterns=["hashmap"])
    assert results == []


def test_search_keeps_a_solution_sharing_any_main_pattern(tmp_path):
    """Main patterns are equal, so sharing any one of them is enough to be compared."""
    conn = make_db(tmp_path)
    add_embedded_solution(conn, 1, unit(1, 0), patterns=("dfs", "dp-knapsack"))
    add_embedded_solution(conn, 2, unit(0.9, 0.4), patterns=("tree",))

    results = embed.search(conn, query(unit(1, 0)), top_k=5, patterns=["dp-knapsack", "math"])
    assert [hit.number for hit in results] == [1]
