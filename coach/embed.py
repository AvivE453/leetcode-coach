import json
import sqlite3
from typing import NamedTuple

import numpy as np

from coach import config


class EmbeddingsUnavailable(Exception):
    """No model to embed with: sentence-transformers isn't installed (it lives in the
    optional `embed` extra), or its model can't be loaded."""


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
        # A failed download and a missing or corrupt cached copy are all OSErrors.
        try:
            _model = SentenceTransformer(config.EMBED_MODEL)
        except OSError as e:
            raise EmbeddingsUnavailable(f"could not load {config.EMBED_MODEL}: {e}") from e
    return np.asarray(_model.encode(texts, normalize_embeddings=True), dtype=np.float32)


def store(conn: sqlite3.Connection, solution_id: int, vector: np.ndarray) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO embeddings (solution_id, vector) VALUES (?, ?)",
        (solution_id, vector.astype(np.float32).tobytes()),
    )


def discard(conn: sqlite3.Connection, solution_id: int) -> None:
    conn.execute("DELETE FROM embeddings WHERE solution_id = ?", (solution_id,))


def to_embed(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Tagged solutions with no vector: tagged while the model was unavailable, or
    re-tagged since, because saving new tags discards the vector of the old ones."""
    return conn.execute(
        """
        SELECT s.id AS solution_id, s.code, p.title, en.main_patterns, en.key_trick
        FROM solutions s
        JOIN problems p ON p.number = s.problem_number
        JOIN enrichments en ON en.solution_id = s.id
        LEFT JOIN embeddings em ON em.solution_id = s.id
        WHERE em.solution_id IS NULL
        ORDER BY s.id
        """
    ).fetchall()


class Hit(NamedTuple):
    """One solved problem's best match: the solve whose vector scored highest, and its score."""

    number: int
    solution_id: int
    score: float


def search(
    conn: sqlite3.Connection,
    queries: np.ndarray,
    top_k: int = 5,
    exclude_problem: int | None = None,
    patterns: list[str] | None = None,
) -> list[Hit]:
    """Each solved problem's best-matching solve, best score first. Vectors are unit-norm.

    `queries` holds one vector per row, and a stored solve scores its best cosine against
    any of them: a problem solved two ways asks through both solves, so the relatives of
    each approach are found. A problem is represented by its best-scoring solve - the
    latest on a tie - and the hit names that solve, so it is described by the approach
    that matched rather than by whichever solve came last.

    With `patterns` set, only solutions sharing at least one of those main patterns
    are considered - the embedding then ranks *within* them instead of across every
    pattern, so an unrelated pattern never wins just for being the least-bad match.
    """
    rows = conn.execute(
        """
        SELECT e.solution_id, e.vector, s.problem_number, en.main_patterns
        FROM embeddings e
        JOIN solutions s ON s.id = e.solution_id
        JOIN enrichments en ON en.solution_id = s.id
        ORDER BY e.solution_id
        """
    ).fetchall()

    best: dict[int, Hit] = {}
    for row in rows:
        number = row["problem_number"]
        if number == exclude_problem:
            continue
        if patterns is not None and set(patterns).isdisjoint(json.loads(row["main_patterns"])):
            continue
        vector = np.frombuffer(row["vector"], dtype=np.float32)
        score = float(np.max(queries @ vector))
        if number not in best or score >= best[number].score:
            best[number] = Hit(number, row["solution_id"], score)

    return sorted(best.values(), key=lambda hit: hit.score, reverse=True)[:top_k]
