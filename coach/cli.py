"""The commands that have no page in the web UI.

Daily use is the web UI (`coach-web`): logging a solve, reviews, the daily plan, the
weekly review and stats all live there, over the same coach/service.py. What stays
here is setup (`init`), the offline backfill (`enrich`), and similarity search (`similar`).
"""

import json
import sys

import numpy as np
import typer

from coach import catalog, config, curriculum, db, embed, enrich, llm, service

app = typer.Typer(no_args_is_help=True)


@app.command()
def init(
    refresh: bool = typer.Option(False, "--refresh", help="Re-download the problem catalog from leetcode.com"),
):
    """Create the database, load the problem catalog, and flag curriculum problems."""
    if refresh or not config.CATALOG_PATH.exists():
        typer.echo("Downloading problem catalog from leetcode.com ...")
        problems = catalog.fetch()
        catalog.save(problems)
        typer.echo(f"Saved {len(problems)} problems to {config.CATALOG_PATH}")

    problems = catalog.load()
    conn = db.connect()
    db.init_schema(conn)
    db.upsert_problems(
        conn,
        [
            {
                "number": p["number"],
                "slug": p["slug"],
                "title": p["title"],
                "difficulty": p["difficulty"],
                "official_tags": json.dumps(p["tags"]),
                "paid_only": int(p["paid_only"]),
            }
            for p in problems
        ],
    )
    flagged = curriculum.apply_flags(conn)

    typer.echo(f"Database ready: {len(problems)} problems")
    for name, count in flagged.items():
        expected = len(curriculum.load(name))
        marker = "" if count == expected else f"  (WARNING: {expected - count} slugs not found in catalog)"
        typer.echo(f"  {name}: {count}/{expected} flagged{marker}")


def echo_neighbors(neighbors: list[service.Neighbor]) -> None:
    for i, n in enumerate(neighbors, 1):
        typer.echo(f"  {i}. #{n.number} {n.title} [{n.difficulty}]  {n.score:.2f}")
        if n.pattern:
            typer.echo(f"     {n.pattern}: {n.key_trick}")


@app.command()
def similar(
    number: int = typer.Argument(None, help="A solved problem number"),
    paste: bool = typer.Option(False, "--paste", help="Paste a problem statement instead"),
    top: int = typer.Option(5, "--top", "-k", help="How many neighbors to show"),
):
    """Find solved problems similar to a problem number or a pasted statement."""
    if paste == (number is not None):
        typer.echo("Pass exactly one of: a problem number, or --paste.")
        raise typer.Exit(1)

    conn = db.connect()
    if number is not None:
        row = conn.execute(
            """
            SELECT e.vector FROM solutions s JOIN embeddings e ON e.solution_id = s.id
            WHERE s.problem_number = ? ORDER BY s.id DESC LIMIT 1
            """,
            (number,),
        ).fetchone()
        if row is None:
            typer.echo(f"No embedded solution for #{number} - log it, or run `coach enrich`.")
            raise typer.Exit(1)
        query = np.frombuffer(row["vector"], dtype=np.float32)
    else:
        if sys.stdin.isatty():
            typer.echo("Paste the problem statement, then press Ctrl+D:")
        statement = sys.stdin.read().strip()
        if not statement:
            typer.echo("No statement received.")
            raise typer.Exit(1)
        try:
            card = enrich.hypothesize(statement)
            text = f"pattern: {card.pattern}\ntrick: {card.key_trick}\n\n{statement}"
            typer.echo(f"Predicted pattern: {card.pattern}")
        except llm.LLMUnavailable as exc:
            typer.echo(f"Pattern prediction skipped ({exc}) - matching on the raw statement.")
            text = statement
        query = embed.encode([text])[0]

    neighbors = embed.search(conn, query, top_k=top, exclude_problem=number)
    if not neighbors:
        typer.echo("No embedded solutions to compare against yet.")
        return
    echo_neighbors(service.neighbor_details(conn, neighbors))


@app.command("enrich")
def enrich_cmd():
    """Backfill pattern tags and embeddings for solutions logged without them."""
    conn = db.connect()
    todo = enrich.missing(conn)
    done = 0
    for row in todo:
        tagged = service.tag_solution_now(conn, row["solution_id"], row, row["code"])
        if tagged.skipped:
            typer.echo(f"Stopped at #{row['number']}: {tagged.skipped}")
            break
        mismatch = f"  (canonical: {tagged.intended_pattern})" if tagged.off_pattern else ""
        typer.echo(f"#{row['number']} {row['title']}: {tagged.pattern} · {tagged.key_trick}{mismatch}")
        done += 1
    typer.echo(f"Enriched {done}/{len(todo)} solution(s).")

    # Read from the database rather than from this run's results, so a solution
    # tagged by an earlier run that stopped before embedding is picked up too.
    pending = conn.execute(
        """
        SELECT s.id AS solution_id, s.code, p.title, en.pattern, en.key_trick
        FROM solutions s
        JOIN problems p ON p.number = s.problem_number
        JOIN enrichments en ON en.solution_id = s.id
        LEFT JOIN embeddings em ON em.solution_id = s.id
        WHERE em.solution_id IS NULL
        ORDER BY s.id
        """
    ).fetchall()
    if pending:
        try:
            vectors = embed.encode(
                [embed.card_text(r["title"], r["pattern"], r["key_trick"], r["code"]) for r in pending]
            )
        except embed.EmbeddingsUnavailable as exc:
            typer.echo(f"Embeddings skipped ({exc})")
            return
        for row, vector in zip(pending, vectors):
            embed.store(conn, row["solution_id"], vector)
        conn.commit()
        typer.echo(f"Embedded {len(pending)} solution(s).")


if __name__ == "__main__":
    app()
