import numpy as np

from coach import db, embed


def unit(x, y):
    v = np.array([x, y], dtype=np.float32)
    return v / np.linalg.norm(v)


def make_db(tmp_path):
    conn = db.connect(tmp_path / "test.db")
    db.init_schema(conn)
    return conn


def add_embedded_solution(conn, number, vector):
    if not conn.execute("SELECT 1 FROM problems WHERE number = ?", (number,)).fetchone():
        conn.execute(
            "INSERT INTO problems (number, slug, title, difficulty) VALUES (?, ?, ?, 'Easy')",
            (number, f"p{number}", f"Problem {number}"),
        )
    solution_id = conn.execute(
        "INSERT INTO solutions (problem_number, code, created_at) VALUES (?, 'c', '2026-01-01')",
        (number,),
    ).lastrowid
    embed.store(conn, solution_id, vector)


def test_card_text_contains_all_parts():
    card = embed.card_text("Two Sum", "hashmap", "complements", "def f(): ...")
    for part in ["Two Sum", "hashmap", "complements", "def f()"]:
        assert part in card


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
