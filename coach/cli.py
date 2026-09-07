import json
import sqlite3
import sys
from datetime import date
from enum import Enum
from pathlib import Path

import numpy as np
import typer

from coach import catalog, config, curriculum, db, embed, enrich, llm, mastery, service

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
    # Rebuilds pattern_scores from whatever history the database already holds,
    # so this is also the repair path if that cache is ever wrong.
    mastery.recompute_all(conn)

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
    problem = service.get_problem(conn, number)
    if problem is None:
        typer.echo(f"Problem {number} not found in the catalog - run `coach init` first?")
        raise typer.Exit(1)

    code = read_solution_code(file).strip()
    if not code:
        typer.echo("No solution code received - nothing logged.")
        raise typer.Exit(1)

    result = service.log_solve(conn, number, outcome.value, code, minutes=time, note=note)

    detail = outcome.value + (f", {time}m" if time else "")
    typer.echo(f"Logged #{number} {problem['title']} ({detail})")
    typer.echo(f"Next review: {result.next_due.isoformat()}")
    echo_enrichment(conn, service.enrich_solution_now(conn, result.solution_id, problem, code))


def echo_enrichment(conn: sqlite3.Connection, e: service.EnrichResult) -> None:
    """Print what post-log enrichment found, including how it degraded."""
    if e.skipped:
        typer.echo(f"Enrichment skipped ({e.skipped}) - run `coach enrich` to backfill later.")
        return
    secondary = f" (+ {', '.join(e.secondary_patterns)})" if e.secondary_patterns else ""
    typer.echo(f"Pattern: {e.pattern}{secondary} · {e.key_trick}")
    echo_standing(service.pattern_standing(conn, e.pattern))
    if e.off_pattern:
        typer.echo(f"Note: the canonical approach is {e.intended_pattern} - worth re-solving that way.")
    echo_also_solvable(e.also_solvable_with)
    if e.embed_skipped:
        typer.echo(f"Embedding skipped ({e.embed_skipped})")
        return
    if e.neighbors:
        typer.echo("Similar solved problems:")
        echo_neighbors(e.neighbors)
    else:
        typer.echo(f"No other solved problems tagged as {e.pattern} yet.")


def echo_also_solvable(patterns: list[str]) -> None:
    """The canonical approaches this solve did not use - shown whether or not the
    off-pattern warning fired, and costing nothing extra to compute."""
    if patterns:
        typer.echo(f"This problem can also be solved with: {', '.join(patterns)}")


def echo_standing(standing: service.PatternStanding | None) -> None:
    """How this pattern is going overall - the weekly analysis, one solve early."""
    if standing is None:
        return
    mastery_note = f"mastery {standing.score:.1f}/5" if standing.score is not None else "unscored"
    if not standing.enough_data:
        plural = "" if standing.attempts == 1 else "s"
        typer.echo(
            f"Standing: {standing.pattern} - {mastery_note} over only {standing.attempts}"
            f" attempt{plural}, too early to call."
        )
        return
    verdict = "WEAK" if standing.weak else "on track"
    typer.echo(
        f"Standing: {standing.pattern} is {verdict} - {mastery_note}, "
        f"{standing.struggle_rate:.0%} struggle rate over {standing.attempts} attempts."
    )


def echo_neighbors(neighbors: list[service.Neighbor]) -> None:
    for i, n in enumerate(neighbors, 1):
        typer.echo(f"  {i}. #{n.number} {n.title} [{n.difficulty}]  {n.score:.2f}")
        if n.pattern:
            typer.echo(f"     {n.pattern}: {n.key_trick}")


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
    echo_neighbors(service.neighbor_details(conn, neighbors))


@app.command("review")
def review_cmd(
    number: int = typer.Argument(help="LeetCode problem number"),
    refresh: bool = typer.Option(False, "--refresh", help="Re-run the review instead of showing the stored one"),
):
    """Feedback on your latest stored solution: strengths, bugs, better approach.

    Stored after the first run, so looking at it again costs nothing.
    """
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
    result = service.review_solution_now(
        conn, solution["id"], problem, solution["code"], refresh=refresh
    )
    if result.skipped:
        typer.echo(f"Review unavailable: {result.skipped}")
        raise typer.Exit(1)

    r = result.review
    if result.cached:
        typer.echo("(stored review - use --refresh to re-run it)")
    typer.echo(f"Verdict: {r.verdict}")
    typer.echo(f"Complexity: {r.time_complexity} time / {r.space_complexity} space"
               f" (optimal: {r.optimal_time_complexity})")
    if r.strengths:
        typer.echo("What went well:")
        for strength in r.strengths:
            typer.echo(f"  + {strength}")
    if r.issues:
        typer.echo("Issues:")
        for issue in r.issues:
            typer.echo(f"  [{issue.category}] {issue.description}")
    else:
        typer.echo("Issues: none found")
    if r.better_approach:
        typer.echo(f"Better approach: {r.better_approach}")
    echo_also_solvable(service.also_solvable_with(conn, solution["id"], problem))


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
        enrich.save_intended(
            conn, row["number"], e.intended_pattern, list(e.intended_secondary_patterns)
        )
        conn.commit()
        mismatch = ""
        if enrich.off_pattern(
            e.pattern, e.secondary_patterns, e.intended_pattern, e.intended_secondary_patterns
        ):
            mismatch = f"  (canonical: {e.intended_pattern})"
        typer.echo(f"#{row['number']} {row['title']}: {e.pattern} · {e.key_trick}{mismatch}")
        done += 1
    if done:
        mastery.recompute_all(conn)
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
    s = service.stats_summary(conn, date.today())
    if s["catalog"] == 0:
        typer.echo("No problems in the database yet - run `coach init` first.")
        raise typer.Exit(1)

    typer.echo(f"Catalog: {s['catalog']} problems")
    typer.echo(
        f"Solved: {s['solved']} distinct problems"
        f" ({s['attempts']} attempts, {s['last_7_days']} in the last 7 days)"
    )
    typer.echo(f"Due for review: {s['due_today']}")

    if s["outcomes"]:
        typer.echo("Outcomes: " + ", ".join(f"{r['outcome']} {r['count']}" for r in s["outcomes"]))

    if s["patterns"]:
        typer.echo("Patterns practiced (by your solutions):")
        for r in s["patterns"]:
            score = f"mastery {r['score']:.1f}/5" if r["score"] is not None else "unscored"
            typer.echo(
                f"  {r['pattern']}: {score}, {r['attempts']} attempt(s), {r['rough']} not clean"
            )

    if s["off_pattern"]:
        typer.echo("Solved off-pattern (canonical approach never used):")
        for r in s["off_pattern"]:
            typer.echo(f"  #{r['number']} {r['title']} -> {r['intended_pattern']}")

    for name, progress in s["curriculum"].items():
        typer.echo(f"{name}: {progress['done']}/{progress['total']}")


def require_catalog(conn: sqlite3.Connection) -> None:
    if conn.execute("SELECT COUNT(*) FROM problems").fetchone()[0] == 0:
        typer.echo("No problem catalog in the database - run `coach init` first.")
        raise typer.Exit(1)


def echo_weekly_run(result: service.WeeklyRunResult) -> None:
    """The outcome of one generated report - printed by `weekly` and by `today`."""
    if result.narrative_skipped:
        typer.echo(f"Narrative skipped ({result.narrative_skipped}) - writing the report without it.")
    typer.echo(
        f"Week {result.week}: {result.attempts} attempt(s), {result.due} review(s) due."
    )
    if result.weak_patterns:
        typer.echo("Weak patterns: " + ", ".join(result.weak_patterns))
    typer.echo(f"Report written to {result.path.relative_to(config.PROJECT_ROOT)}"
               + (" (degraded: no narrative)" if result.degraded else ""))


@app.command()
def today(
    target: int = typer.Option(config.DAILY_TARGET, "--target", help="Problems to plan for today"),
):
    """Today's problems, in priority order. Writes the weekly review once a week.

    The list itself is free - pure SQL, recomputed every run, so solved problems
    drop off and the next one takes the slot. The first run of each ISO week also
    generates reports/YYYY-WW.md, which is the only call that costs anything.
    """
    conn = db.connect()
    require_catalog(conn)

    now = date.today()
    items = service.daily_plan(conn, now, target)
    if items:
        typer.echo(f"{len(items)} problem(s) for today:")
        for item in items:
            typer.echo(f"  #{item.number} {item.title} [{item.difficulty}]  {item.reason}")
    else:
        typer.echo("Nothing to do today - no reviews due and the curriculum is finished.")

    if service.weekly_report_needed(conn, now):
        typer.echo("")
        typer.echo("First run this week - writing the weekly review ...")
        echo_weekly_run(service.run_weekly(conn, now))


@app.command()
def weekly(
    no_llm: bool = typer.Option(False, "--no-llm", help="Skip the narrative call (offline report)"),
):
    """Write reports/YYYY-WW.md by hand: the week's solves, the patterns, the note.

    `coach today` already does this once a week; this is for running it early or offline.
    """
    conn = db.connect()
    require_catalog(conn)
    echo_weekly_run(service.run_weekly(conn, date.today(), no_llm=no_llm))


if __name__ == "__main__":
    app()
