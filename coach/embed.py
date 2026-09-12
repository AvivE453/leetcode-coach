import json
import sqlite3

import numpy as np

from coach import config


class EmbeddingsUnavailable(Exception):
    """sentence-transformers isn't installed (it lives in the optional `embed` extra)."""


def card_text(title: str, main_patterns: list[str], key_trick: str, code: str) -> str:
    return f"{title}\npattern: {', '.join(main_patterns)}\ntrick: {key_trick}\n\n{code}"


_model = None


def encode(texts: list[str]) -> np.ndarray:
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise EmbeddingsUnavailable(
                "sentence-transformers not installed - run: uv sync --extra embed"
            ) from e
        _model = SentenceTransformer(config.EMBED_MODEL)
    return np.asarray(_model.encode(texts, normalize_embeddings=True), dtype=np.float32)


def store(conn: sqlite3.Connection, solution_id: int, vector: np.ndarray) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO embeddings (solution_id, vector) VALUES (?, ?)",
        (solution_id, vector.astype(np.float32).tobytes()),
    )


def search(
    conn: sqlite3.Connection,
    query: np.ndarray,
    top_k: int = 5,
    exclude_problem: int | None = None,
    patterns: list[str] | None = None,
) -> list[tuple[int, float]]:
    """Best cosine score per solved problem, descending. Vectors are unit-norm.

    With `patterns` set, only solutions sharing at least one of those main patterns
    are considered - the embedding then ranks *within* them instead of across every
    pattern, so an unrelated pattern never wins just for being the least-bad match.
    """
    rows = conn.execute(
        """
        SELECT e.vector, s.problem_number, en.main_patterns
        FROM embeddings e
        JOIN solutions s ON s.id = e.solution_id
        JOIN enrichments en ON en.solution_id = s.id
        """
    ).fetchall()

    best: dict[int, float] = {}
    for row in rows:
        number = row["problem_number"]
        if number == exclude_problem:
            continue
        if patterns is not None and set(patterns).isdisjoint(json.loads(row["main_patterns"])):
            continue
        vector = np.frombuffer(row["vector"], dtype=np.float32)
        score = float(np.dot(vector, query))
        if score > best.get(number, -2.0):
            best[number] = score

    ranked = sorted(best.items(), key=lambda item: item[1], reverse=True)
    return ranked[:top_k]
