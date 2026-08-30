import json
import sys
from datetime import date, timedelta
from enum import Enum
from pathlib import Path

import typer

from coach import catalog, config, curriculum, db, scheduler

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
    conn.execute(
        "INSERT INTO solutions (problem_number, attempt_id, code, created_at, file_path) VALUES (?, ?, ?, ?, ?)",
        (number, cursor.lastrowid, code, today.isoformat(), str(path.relative_to(config.PROJECT_ROOT))),
    )
    state = update_review_state(conn, number, outcome.value, today)
    conn.commit()

    detail = outcome.value + (f", {time}m" if time else "")
    typer.echo(f"Logged #{number} {problem['title']} ({detail})")
    typer.echo(f"Solution saved to {path.name}. Next review: {state.next_due.isoformat()}")


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
