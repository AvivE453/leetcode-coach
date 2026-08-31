import json
import sys
from datetime import date, timedelta
from enum import Enum
from pathlib import Path

import numpy as np
import typer

from coach import catalog, config, curriculum, db, embed, enrich, llm, scheduler
from coach import review as review_llm

app = typer.Typer(no_args_is_help=True)


class Outcome(str, Enum):
    clean = "clean"
    struggled = "struggled"
    hints = "hints"
    failed = "failed"


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


def read_solution_code(file: Path | None) -> str:
    if file:
        return file.read_text()
    if sys.stdin.isatty():
        typer.echo("Paste your solution, then press Ctrl+D:")
    return sys.stdin.read()


def append_to_solution_file(problem, code: str, today: str, outcome: str, minutes: int | None) -> Path:
    config.SOLUTIONS_DIR.mkdir(parents=True, exist_ok=True)
    path = config.SOLUTIONS_DIR / f"{problem['number']:04d}-{problem['slug']}.py"
    if not path.exists():
        path.write_text(
            f"# {problem['number']}. {problem['title']}\n"
            f"# https://leetcode.com/problems/{problem['slug']}/\n"
        )
    header = f"\n# --- {today} · {outcome}" + (f" · {minutes}m" if minutes else "") + "\n"
    with path.open("a") as f:
        f.write(header + code.rstrip() + "\n")
    return path


def update_review_state(conn, number: int, outcome: str, today: date) -> scheduler.ReviewState:
    row = conn.execute(
        "SELECT * FROM review_state WHERE problem_number = ?", (number,)
    ).fetchone()
    state = (
        scheduler.ReviewState(
            ease=row["ease"],
            interval_days=row["interval_days"],
            next_due=date.fromisoformat(row["next_due"]),
            reps=row["reps"],
            lapses=row["lapses"],
        )
        if row
        else None
    )
    new = scheduler.review(state, outcome, today)
    conn.execute(
        """
        INSERT INTO review_state (problem_number, ease, interval_days, next_due, reps, lapses)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(problem_number) DO UPDATE SET
            ease = excluded.ease,
            interval_days = excluded.interval_days,
            next_due = excluded.next_due,
            reps = excluded.reps,
            lapses = excluded.lapses
        """,
        (number, new.ease, new.interval_days, new.next_due.isoformat(), new.reps, new.lapses),
    )
    return new


@app.command()
def log(
    number: int = typer.Argument(help="LeetCode problem number"),
    outcome: Outcome = typer.Option(Outcome.clean, "--outcome", "-o", help="How the solve went"),
    time: int = typer.Option(None, "--time", "-t", help="Minutes spent"),
    note: str = typer.Option(None, "--note"),
    file: Path = typer.Option(None, "--file", "-f", help="Read the solution from a file instead of pasting"),
):
    """Log a solve: stores the attempt + solution and updates the review schedule."""
    conn = db.connect()
    problem = conn.execute("SELECT * FROM problems WHERE number = ?", (number,)).fetchone()
    if problem is None:
        typer.echo(f"Problem {number} not found in the catalog - run `coach init` first?")
        raise typer.Exit(1)

    code = read_solution_code(file).strip()
    if not code:
        typer.echo("No solution code received - nothing logged.")
        raise typer.Exit(1)

    today = date.today()
    cursor = conn.execute(
        "INSERT INTO attempts (problem_number, date, outcome, minutes, note) VALUES (?, ?, ?, ?, ?)",
        (number, today.isoformat(), outcome.value, time, note),
    )
    path = append_to_solution_file(problem, code, today.isoformat(), outcome.value, time)
    solution_id = conn.execute(
        "INSERT INTO solutions (problem_number, attempt_id, code, created_at, file_path) VALUES (?, ?, ?, ?, ?)",
        (number, cursor.lastrowid, code, today.isoformat(), str(path.relative_to(config.PROJECT_ROOT))),
    ).lastrowid
    state = update_review_state(conn, number, outcome.value, today)
    conn.commit()

    detail = outcome.value + (f", {time}m" if time else "")
    typer.echo(f"Logged #{number} {problem['title']} ({detail})")
    typer.echo(f"Solution saved to {path.name}. Next review: {state.next_due.isoformat()}")
    enrich_and_embed(conn, solution_id, problem, code)


def enrich_and_embed(conn, solution_id: int, problem, code: str) -> None:
    """Post-log enrichment: tag the solution, embed its card, show similar solves."""
    try:
        e = enrich.enrich_solution(problem, code)
    except llm.LLMUnavailable as exc:
        typer.echo(f"Enrichment skipped ({exc}) - run `coach enrich` to backfill later.")
        return
    enrich.save(conn, solution_id, e)
    enrich.save_intended(conn, problem["number"], e.intended_pattern)
    conn.commit()
    secondary = f" (+ {', '.join(e.secondary_patterns)})" if e.secondary_patterns else ""
    typer.echo(f"Pattern: {e.pattern}{secondary} · {e.key_trick}")
    if e.intended_pattern != e.pattern and e.intended_pattern not in e.secondary_patterns:
        typer.echo(f"Note: the canonical approach is {e.intended_pattern} - worth re-solving that way.")

    try:
        vector = embed.encode([embed.card_text(problem["title"], e.pattern, e.key_trick, code)])[0]
    except embed.EmbeddingsUnavailable as exc:
        typer.echo(f"Embedding skipped ({exc})")
        return
    embed.store(conn, solution_id, vector)
    conn.commit()

    neighbors = embed.search(conn, vector, top_k=3, exclude_problem=problem["number"])
    if neighbors:
        typer.echo("Similar solved problems:")
        echo_neighbors(conn, neighbors)


def echo_neighbors(conn, neighbors: list[tuple[int, float]]) -> None:
    for i, (number, score) in enumerate(neighbors, 1):
        p = conn.execute(
            "SELECT title, difficulty FROM problems WHERE number = ?", (number,)
        ).fetchone()
        typer.echo(f"  {i}. #{number} {p['title']} [{p['difficulty']}]  {score:.2f}")
        en = conn.execute(
            """
            SELECT en.pattern, en.key_trick
            FROM solutions s JOIN enrichments en ON en.solution_id = s.id
            WHERE s.problem_number = ? ORDER BY s.id DESC LIMIT 1
            """,
            (number,),
        ).fetchone()
        if en:
            typer.echo(f"     {en['pattern']}: {en['key_trick']}")


@app.command()
def due():
    """Problems whose review is due today (or overdue)."""
    conn = db.connect()
    today = date.today()
    rows = conn.execute(
        """
        SELECT p.number, p.title, p.difficulty, r.next_due
        FROM review_state r JOIN problems p ON p.number = r.problem_number
        WHERE r.next_due <= ?
        ORDER BY r.next_due
        """,
        (today.isoformat(),),
    ).fetchall()
    if not rows:
        typer.echo("Nothing due for review today.")
        return
    typer.echo(f"{len(rows)} problem(s) due for review:")
    for r in rows:
        overdue = (today - date.fromisoformat(r["next_due"])).days
        suffix = f"  (overdue {overdue}d)" if overdue > 0 else ""
        typer.echo(f"  #{r['number']} {r['title']} [{r['difficulty']}]{suffix}")


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
    echo_neighbors(conn, neighbors)


@app.command("review")
def review_cmd(number: int = typer.Argument(help="LeetCode problem number")):
    """LLM feedback on your latest stored solution: complexity, bugs, better approach."""
    conn = db.connect()
    problem = conn.execute("SELECT * FROM problems WHERE number = ?", (number,)).fetchone()
    if problem is None:
        typer.echo(f"Problem {number} not found in the catalog.")
        raise typer.Exit(1)
    solution = conn.execute(
        "SELECT * FROM solutions WHERE problem_number = ? ORDER BY id DESC LIMIT 1", (number,)
    ).fetchone()
    if solution is None:
        typer.echo(f"No stored solution for #{number} - log one with `coach log {number}`.")
        raise typer.Exit(1)

    typer.echo(f"Reviewing #{number} {problem['title']} ...")
    try:
        r = review_llm.review_solution(problem, solution["code"])
    except llm.LLMUnavailable as exc:
        typer.echo(f"Review unavailable: {exc}")
        raise typer.Exit(1) from None

    typer.echo(f"Verdict: {r.verdict}")
    typer.echo(f"Complexity: {r.time_complexity} time / {r.space_complexity} space"
               f" (optimal: {r.optimal_time_complexity})")
    if r.issues:
        typer.echo("Issues:")
        for issue in r.issues:
            typer.echo(f"  [{issue.category}] {issue.description}")
    else:
        typer.echo("Issues: none found")
    if r.better_approach:
        typer.echo(f"Better approach: {r.better_approach}")


@app.command("enrich")
def enrich_cmd(
    missing: bool = typer.Option(True, "--missing", help="Only process solutions without tags (the only mode for now)"),
):
    """Backfill pattern tags and embeddings for solutions logged without them."""
    conn = db.connect()
    todo = enrich.missing(conn)
    done = 0
    for row in todo:
        try:
            e = enrich.enrich_solution(row, row["code"])
        except llm.LLMUnavailable as exc:
            typer.echo(f"Stopped at #{row['number']}: {exc}")
            break
        enrich.save(conn, row["solution_id"], e)
        enrich.save_intended(conn, row["number"], e.intended_pattern)
        conn.commit()
        mismatch = ""
        if e.intended_pattern != e.pattern and e.intended_pattern not in e.secondary_patterns:
            mismatch = f"  (canonical: {e.intended_pattern})"
        typer.echo(f"#{row['number']} {row['title']}: {e.pattern} · {e.key_trick}{mismatch}")
        done += 1
    typer.echo(f"Enriched {done}/{len(todo)} solution(s).")

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


@app.command()
def stats():
    """Progress overview: solved counts, curriculum coverage, recent activity."""
    conn = db.connect()
    total = conn.execute("SELECT COUNT(*) FROM problems").fetchone()[0]
    if total == 0:
        typer.echo("No problems in the database yet - run `coach init` first.")
        raise typer.Exit(1)

    today = date.today()
    solved = conn.execute("SELECT COUNT(DISTINCT problem_number) FROM attempts").fetchone()[0]
    attempts = conn.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
    week = conn.execute(
        "SELECT COUNT(*) FROM attempts WHERE date >= ?",
        ((today - timedelta(days=7)).isoformat(),),
    ).fetchone()[0]
    due_count = conn.execute(
        "SELECT COUNT(*) FROM review_state WHERE next_due <= ?", (today.isoformat(),)
    ).fetchone()[0]

    typer.echo(f"Catalog: {total} problems")
    typer.echo(f"Solved: {solved} distinct problems ({attempts} attempts, {week} in the last 7 days)")
    typer.echo(f"Due for review: {due_count}")

    outcomes = conn.execute(
        "SELECT outcome, COUNT(*) AS n FROM attempts GROUP BY outcome ORDER BY n DESC"
    ).fetchall()
    if outcomes:
        typer.echo("Outcomes: " + ", ".join(f"{r['outcome']} {r['n']}" for r in outcomes))

    patterns = conn.execute(
        """
        SELECT en.pattern, COUNT(*) AS attempts, SUM(a.outcome != 'clean') AS rough
        FROM attempts a
        JOIN solutions s ON s.attempt_id = a.id
        JOIN enrichments en ON en.solution_id = s.id
        GROUP BY en.pattern
        ORDER BY attempts DESC, en.pattern
        """
    ).fetchall()
    if patterns:
        typer.echo("Patterns practiced (by your solutions):")
        for r in patterns:
            typer.echo(f"  {r['pattern']}: {r['attempts']} attempt(s), {r['rough']} not clean")

    off_pattern = conn.execute(
        """
        SELECT p.number, p.title, p.intended_pattern
        FROM problems p
        WHERE p.intended_pattern IS NOT NULL
          AND NOT EXISTS (
            SELECT 1
            FROM solutions s JOIN enrichments en ON en.solution_id = s.id
            WHERE s.problem_number = p.number
              AND (en.pattern = p.intended_pattern
                   OR en.secondary_patterns LIKE '%"' || p.intended_pattern || '"%')
          )
        ORDER BY p.number
        """
    ).fetchall()
    if off_pattern:
        typer.echo("Solved off-pattern (canonical approach never used):")
        for r in off_pattern:
            typer.echo(f"  #{r['number']} {r['title']} -> {r['intended_pattern']}")

    for name, column in curriculum.FLAG_COLUMNS.items():
        in_list = conn.execute(f"SELECT COUNT(*) FROM problems WHERE {column} = 1").fetchone()[0]
        done = conn.execute(
            f"""
            SELECT COUNT(DISTINCT a.problem_number)
            FROM attempts a JOIN problems p ON p.number = a.problem_number
            WHERE p.{column} = 1
            """
        ).fetchone()[0]
        typer.echo(f"{name}: {done}/{in_list}")


if __name__ == "__main__":
    app()
