import sqlite3

import numpy as np

from coach import config


class EmbeddingsUnavailable(Exception):
    """sentence-transformers isn't installed (it lives in the optional `embed` extra)."""


def card_text(title: str, pattern: str, key_trick: str, code: str) -> str:
    return f"{title}\npattern: {pattern}\ntrick: {key_trick}\n\n{code}"


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
    pattern: str | None = None,
) -> list[tuple[int, float]]:
    """Best cosine score per solved problem, descending. Vectors are unit-norm.

    With `pattern` set, only solutions tagged with that pattern are considered -
    the embedding then ranks *within* the pattern instead of across all of them,
    so an unrelated pattern never wins just for being the least-bad match.
    """
    rows = conn.execute(
        """
        SELECT e.vector, s.problem_number, en.pattern
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
        if pattern is not None and row["pattern"] != pattern:
            continue
        vector = np.frombuffer(row["vector"], dtype=np.float32)
        score = float(np.dot(vector, query))
        if score > best.get(number, -2.0):
            best[number] = score

    ranked = sorted(best.items(), key=lambda item: item[1], reverse=True)
    return ranked[:top_k]
