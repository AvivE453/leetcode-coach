"""FastAPI wrapper around coach/service.py — the backend of the daily interface.

Every endpoint is a thin JSON translation of a service function. The CLI keeps only
the jobs with no page (init, enrich, similar), over the same service functions. The
two write endpoints are POST /api/log and POST /api/solutions/{number}/review.
"""

from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Literal

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from coach import config, db, mastery, service
from coach.weekly import analyze as weekly_analyze

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="leetcode-coach", docs_url="/api/docs", redoc_url=None)


@contextmanager
def open_db():
    """One SQLite connection per request, opened inside the endpoint.

    It must not be a FastAPI dependency: sync dependencies and sync endpoints
    run as separate threadpool tasks, so the connection would be created on one
    thread and used on another - which SQLite refuses under concurrent load.
    """
    conn = db.connect()
    try:
        yield conn
    finally:
        conn.close()


def thresholds() -> dict:
    """The numbers that decide weak and stale.

    Served so each page can word its own empty states from the constants rather
    than restating them in English, where they go stale silently.
    """
    return {
        "weak_score": mastery.WEAK_SCORE,
        "weak_min_attempts": mastery.WEAK_MIN_ATTEMPTS,
        "stale_days": weekly_analyze.STALE_DAYS,
    }


class LogRequest(BaseModel):
    number: int = Field(gt=0)
    outcome: Literal["clean", "struggled", "hints", "failed"]
    code: str
    minutes: int | None = Field(default=None, ge=0)
    note: str | None = None


@app.get("/api/stats")
def api_stats() -> dict:
    with open_db() as conn:
        summary = service.stats_summary(conn, date.today())
    summary["db"] = str(config.DB_PATH)
    return summary


@app.get("/api/patterns")
def api_patterns() -> dict:
    with open_db() as conn:
        return {"patterns": service.pattern_table(conn)}


@app.post("/api/log")
def api_log(body: LogRequest) -> dict:
    """Log a solve, then enrich it. A saved solve is never an error: if the LLM
    or the embedding model is unavailable the response says so and the solve
    still stands (`coach enrich` backfills later)."""
    with open_db() as conn:
        problem = service.get_problem(conn, body.number)
        if problem is None:
            raise HTTPException(
                404, f"Problem {body.number} is not in the catalog - run `coach init` first?"
            )
        if not body.code.strip():
            raise HTTPException(400, "No solution code received - nothing logged.")

        result = service.log_solve(
            conn, body.number, body.outcome, body.code, minutes=body.minutes, note=body.note
        )
        e = service.enrich_solution_now(conn, result.solution_id, problem, body.code.strip())
        standings = service.pattern_standings(conn, e.main_patterns)

    return {
        "number": result.number,
        "title": result.title,
        "difficulty": problem["difficulty"],
        "outcome": result.outcome,
        "next_due": result.next_due.isoformat(),
        "enrichment": {
            "status": "skipped" if e.skipped else "ok",
            "reason": e.skipped,
            "main_patterns": e.main_patterns,
            "secondary_patterns": e.secondary_patterns,
            "key_trick": e.key_trick,
            "intended_pattern": e.intended_pattern,
            "intended_secondary_patterns": e.intended_secondary_patterns,
            "off_pattern": e.off_pattern,
            "also_solvable_with": e.also_solvable_with,
            "embedding_skipped": e.embed_skipped,
            "neighbors": [
                {
                    "number": n.number,
                    "title": n.title,
                    "difficulty": n.difficulty,
                    "score": round(n.score, 3),
                    "main_patterns": n.main_patterns,
                    "key_trick": n.key_trick,
                }
                for n in e.neighbors
            ],
        },
        "pattern_standings": [
            {
                "pattern": s.pattern,
                "attempts": s.attempts,
                "struggle_rate": round(s.struggle_rate, 3),
                "score": round(s.score, 2),
                "weak": s.weak,
                "enough_data": s.enough_data,
            }
            for s in standings
        ],
    }


@app.get("/api/solutions")
def api_solutions(q: str = "") -> dict:
    with open_db() as conn:
        return service.solutions_listing(conn, q)


@app.get("/api/solutions/{number}")
def api_solution_history(number: int) -> dict:
    with open_db() as conn:
        try:
            return service.solution_history(conn, number)
        except service.ProblemNotFound:
            raise HTTPException(
                404, f"Problem {number} is not in the catalog - run `coach init` first?"
            ) from None


class ReviewRequest(BaseModel):
    solution_id: int = Field(gt=0)
    refresh: bool = False


@app.post("/api/solutions/{number}/review")
def api_review(number: int, body: ReviewRequest) -> dict:
    """Review one stored solve. POST because it can spend money and it writes.

    A solve that already has a stored review costs nothing - the store is checked
    before any API call.
    """
    with open_db() as conn:
        problem = service.get_problem(conn, number)
        if problem is None:
            raise HTTPException(
                404, f"Problem {number} is not in the catalog - run `coach init` first?"
            )
        solution = conn.execute(
            "SELECT id, code FROM solutions WHERE id = ? AND problem_number = ?",
            (body.solution_id, number),
        ).fetchone()
        if solution is None:
            raise HTTPException(404, f"No stored solution {body.solution_id} for ({number}).")

        result = service.review_solution_now(
            conn, solution["id"], problem, solution["code"], refresh=body.refresh
        )

    return {
        "solution_id": body.solution_id,
        "status": "skipped" if result.skipped else "ok",
        "reason": result.skipped,
        "cached": result.cached,
        "review": service.review_payload(result.review) if result.review else None,
    }


@app.get("/api/plan")
def api_plan(target: int = config.DAILY_TARGET) -> dict:
    """Recompute today's plan live. Read-only, and stored nowhere."""
    today = date.today()
    with open_db() as conn:
        plan = service.daily_plan(conn, today, target)
    items, analysis = plan.items, plan.analysis

    return {
        "generated_for": today.isoformat(),
        "target": target,
        "items": [
            {
                "number": i.number,
                "slug": i.slug,
                "title": i.title,
                "difficulty": i.difficulty,
                "reason": i.reason,
                "kind": i.kind,
            }
            for i in items
        ],
        "topics": {
            "weak": analysis["weak_patterns"],
            "stale": analysis["stale_patterns"],
            "off_pattern": [
                {
                    "number": r["number"],
                    "title": r["title"],
                    "intended_pattern": r["intended_pattern"],
                }
                for r in analysis["off_pattern"]
            ],
        },
        "due_count": len(analysis["due"]),
        "curriculum": analysis["curriculum"],
        "thresholds": thresholds(),
    }


@app.get("/api/weekly")
def api_weekly() -> dict:
    """The last seven days, recomputed on every call.

    Free to open, like every other page: pure SQL, no LLM call, and nothing is
    written - so logging a solve is visible here immediately.
    """
    with open_db() as conn:
        review = service.weekly_review(conn, date.today())

    return {
        "start": review.start.isoformat(),
        "end": review.end.isoformat(),
        "distinct_problems": review.distinct_problems,
        "attempts": [
            {
                "date": r["date"],
                "number": r["problem_number"],
                "title": r["title"],
                "difficulty": r["difficulty"],
                "outcome": r["outcome"],
                "minutes": r["minutes"],
                "main_patterns": r["main_patterns"],
            }
            for r in review.attempts
        ],
        "patterns": [
            {
                "pattern": p.pattern,
                "attempts_week": p.attempts_week,
                "attempts_total": p.attempts_total,
                "score": p.score,
                "score_before": p.score_before,
                "delta": p.delta,
                "standing": p.standing,
            }
            for p in review.patterns
        ],
        "thresholds": thresholds(),
    }


# A page and the script that drives it are one unit: the script reaches into the
# markup by id, so a cached script paired with fresh markup does not degrade, it
# breaks silently - getElementById returns null, the handler that would report the
# failure reaches for a missing element too, and the page sits on its loading text
# forever. "no-cache" means revalidate, not re-download: the browser still gets a
# 304 when nothing changed, which costs nothing on localhost.
NO_CACHE = {"Cache-Control": "no-cache"}


def page(name: str) -> FileResponse:
    """One of the four HTML pages, revalidated on every load like its script."""
    return FileResponse(STATIC_DIR / name, headers=NO_CACHE)


class RevalidatedStaticFiles(StaticFiles):
    """StaticFiles under the same rule as page() - see NO_CACHE above for why."""

    def file_response(self, *args, **kwargs) -> Response:
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


@app.get("/", include_in_schema=False)
def home() -> FileResponse:
    return page("index.html")


@app.get("/plan", include_in_schema=False)
def plan_page() -> FileResponse:
    return page("plan.html")


@app.get("/solutions", include_in_schema=False)
def solutions_page() -> FileResponse:
    return page("solutions.html")


@app.get("/weekly", include_in_schema=False)
def weekly_page() -> FileResponse:
    return page("weekly.html")


app.mount("/static", RevalidatedStaticFiles(directory=STATIC_DIR), name="static")


def main() -> None:
    """`coach-web` entry point."""
    print(f"leetcode-coach web UI on http://{config.WEB_HOST}:{config.WEB_PORT}")
    print(f"database: {config.DB_PATH}")
    uvicorn.run(app, host=config.WEB_HOST, port=config.WEB_PORT, log_level="info")
