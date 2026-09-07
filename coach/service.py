"""Logic shared by the CLI and the web UI.

Everything here is pure-ish: it takes a connection, touches the database, and
returns data. No printing, no typer, no HTTP. `coach/cli.py` wraps these in
`typer.echo` calls; `coach/web/app.py` serialises them to JSON.
"""

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from coach import config, curriculum, embed, enrich, llm, mastery, scheduler
from coach import review as review_llm
from coach.weekly import analyze as weekly_analyze
from coach.weekly import collect as weekly_collect
from coach.weekly import plan as weekly_plan
from coach.weekly import report as weekly_report

OUTCOMES = ("clean", "struggled", "hints", "failed")


class ProblemNotFound(LookupError):
    """No catalog row for that problem number."""


class EmptySolution(ValueError):
    """A solve was submitted with no code."""


@dataclass(frozen=True)
class LogResult:
    number: int
    title: str
    outcome: str
    minutes: int | None
    solution_id: int
    next_due: date


@dataclass(frozen=True)
class Neighbor:
    number: int
    title: str
    difficulty: str
    score: float
    pattern: str | None = None
    key_trick: str | None = None


@dataclass(frozen=True)
class EnrichResult:
    """What post-log enrichment produced, including how far it got.

    `skipped` / `embed_skipped` carry the degradation reason: a solve is stored
    whether or not the API answers, so neither is an error.
    """

    pattern: str | None = None
    secondary_patterns: list[str] = field(default_factory=list)
    key_trick: str | None = None
    intended_pattern: str | None = None
    intended_secondary_patterns: list[str] = field(default_factory=list)
    off_pattern: bool = False
    also_solvable_with: list[str] = field(default_factory=list)
    neighbors: list[Neighbor] = field(default_factory=list)
    skipped: str | None = None
    embed_skipped: str | None = None


@dataclass(frozen=True)
class ReviewResult:
    """A stored or freshly fetched review, plus how far it got.

    `skipped` carries the degradation reason, like `EnrichResult`: no API key means
    no review, never an error. `cached` says whether this cost anything.
    """

    review: review_llm.Review | None = None
    cached: bool = False
    skipped: str | None = None


@dataclass(frozen=True)
class WeeklyRunResult:
    """One generated weekly report: what was written, and how far it got.

    `narrative_skipped` carries the degradation reason instead of printing it —
    the caller decides how to say it, the same contract as `EnrichResult`.
    """

    path: Path
    week: str
    degraded: bool
    narrative_skipped: str | None
    attempts: int
    due: int
    weak_patterns: list[str]


@dataclass(frozen=True)
class PatternStanding:
    """Where a pattern currently stands, per the existing weekly analyze() aggregates."""

    pattern: str
    attempts: int
    struggle_rate: float
    score: float | None
    weak: bool
    enough_data: bool


def get_problem(conn: sqlite3.Connection, number: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM problems WHERE number = ?", (number,)).fetchone()


def json_list(raw: str | None) -> list[str]:
    return json.loads(raw) if raw else []


def problem_canonical(problem) -> tuple[str | None, list[str]]:
    """A problem row's canonical approaches: (intended, intended_secondary).

    Tolerates a row from before the column existed, so a caller holding an old
    query result still gets the single-pattern behaviour rather than an error.
    """
    try:
        secondary = json_list(problem["intended_secondary_patterns"])
    except (IndexError, KeyError):
        secondary = []
    return problem["intended_pattern"], secondary


def update_review_state(
    conn: sqlite3.Connection, number: int, outcome: str, today: date
) -> scheduler.ReviewState:
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


def log_solve(
    conn: sqlite3.Connection,
    number: int,
    outcome: str,
    code: str,
    minutes: int | None = None,
    note: str | None = None,
    today: date | None = None,
) -> LogResult:
    """Store an attempt + solution and reschedule its review."""
    problem = get_problem(conn, number)
    if problem is None:
        raise ProblemNotFound(number)
    code = code.strip()
    if not code:
        raise EmptySolution(number)

    today = today or date.today()
    cursor = conn.execute(
        "INSERT INTO attempts (problem_number, date, outcome, minutes, note) VALUES (?, ?, ?, ?, ?)",
        (number, today.isoformat(), outcome, minutes, note),
    )
    solution_id = conn.execute(
        "INSERT INTO solutions (problem_number, attempt_id, code, created_at) VALUES (?, ?, ?, ?)",
        (number, cursor.lastrowid, code, today.isoformat()),
    ).lastrowid
    state = update_review_state(conn, number, outcome, today)
    conn.commit()

    return LogResult(
        number=number,
        title=problem["title"],
        outcome=outcome,
        minutes=minutes,
        solution_id=solution_id,
        next_due=state.next_due,
    )


def neighbor_details(conn: sqlite3.Connection, neighbors: list[tuple[int, float]]) -> list[Neighbor]:
    """Attach titles and the latest pattern/trick to raw (number, score) hits."""
    out = []
    for number, score in neighbors:
        p = conn.execute(
            "SELECT title, difficulty FROM problems WHERE number = ?", (number,)
        ).fetchone()
        en = conn.execute(
            """
            SELECT en.pattern, en.key_trick
            FROM solutions s JOIN enrichments en ON en.solution_id = s.id
            WHERE s.problem_number = ? ORDER BY s.id DESC LIMIT 1
            """,
            (number,),
        ).fetchone()
        out.append(
            Neighbor(
                number=number,
                title=p["title"] if p else f"#{number}",
                difficulty=p["difficulty"] if p else "",
                score=score,
                pattern=en["pattern"] if en else None,
                key_trick=en["key_trick"] if en else None,
            )
        )
    return out


def enrich_solution_now(
    conn: sqlite3.Connection, solution_id: int, problem: sqlite3.Row, code: str
) -> EnrichResult:
    """Tag the solution, embed its card, and find similar solves.

    Degrades in two steps: no API key -> `skipped`; no sentence-transformers ->
    `embed_skipped`. Both leave the stored solve untouched.
    """
    try:
        e = enrich.enrich_solution(problem, code)
    except llm.LLMUnavailable as exc:
        return EnrichResult(skipped=str(exc))

    enrich.save(conn, solution_id, e)
    enrich.save_intended(
        conn, problem["number"], e.intended_pattern, list(e.intended_secondary_patterns)
    )
    conn.commit()
    # The pattern only exists now, so this is the first moment the solve can be
    # scored - and pattern_standing() below reads what this writes.
    mastery.recompute_all(conn)

    # canonical[0] is intended_pattern; the rest are the alternates, deduplicated
    # exactly as save_intended stored them, so response and database agree.
    canonical = enrich.canonical_patterns(e.intended_pattern, list(e.intended_secondary_patterns))
    intended_secondary = canonical[1:]
    # Two signals off one free set comparison: off_pattern is the sharp one (no
    # canonical approach used at all), also_solvable_with is informational.
    tagged = {
        "pattern": e.pattern,
        "secondary_patterns": list(e.secondary_patterns),
        "key_trick": e.key_trick,
        "intended_pattern": e.intended_pattern,
        "intended_secondary_patterns": intended_secondary,
        "off_pattern": enrich.off_pattern(
            e.pattern, e.secondary_patterns, e.intended_pattern, intended_secondary
        ),
        "also_solvable_with": enrich.unused_canonical(
            e.pattern, e.secondary_patterns, e.intended_pattern, intended_secondary
        ),
    }

    try:
        vector = embed.encode([embed.card_text(problem["title"], e.pattern, e.key_trick, code)])[0]
    except embed.EmbeddingsUnavailable as exc:
        return EnrichResult(**tagged, embed_skipped=str(exc))

    embed.store(conn, solution_id, vector)
    conn.commit()
    hits = embed.search(conn, vector, top_k=3, exclude_problem=problem["number"], pattern=e.pattern)

    return EnrichResult(**tagged, neighbors=neighbor_details(conn, hits))


def review_solution_now(
    conn: sqlite3.Connection,
    solution_id: int,
    problem: sqlite3.Row,
    code: str,
    refresh: bool = False,
) -> ReviewResult:
    """Feedback on one stored solution, bought once and reused thereafter.

    The stored review is checked before any API call, so looking at a solve you have
    already reviewed is free. `refresh` forces a new call.
    """
    if not refresh:
        stored = review_llm.load(conn, solution_id)
        if stored is not None:
            return ReviewResult(review=stored, cached=True)

    try:
        r = review_llm.review_solution(problem, code)
    except llm.LLMUnavailable as exc:
        return ReviewResult(skipped=str(exc))

    review_llm.save(conn, solution_id, r)
    conn.commit()
    # A review usually lands well after the solve, so this re-scores the attempt
    # it belongs to - the whole reason scores are replayed rather than updated.
    mastery.recompute_all(conn)
    return ReviewResult(review=r)


def also_solvable_with(conn: sqlite3.Connection, solution_id: int, problem) -> list[str]:
    """Canonical approaches one stored solve did not use.

    Computed on read, never stored, so the note stays correct if the problem's
    canonical set widens later. Empty when the solve was never enriched.
    """
    row = conn.execute(
        "SELECT pattern, secondary_patterns FROM enrichments WHERE solution_id = ?",
        (solution_id,),
    ).fetchone()
    if row is None:
        return []
    intended, intended_secondary = problem_canonical(problem)
    return enrich.unused_canonical(
        row["pattern"], json_list(row["secondary_patterns"]), intended, intended_secondary
    )


def pattern_standing(
    conn: sqlite3.Connection, pattern: str | None, today: date | None = None
) -> PatternStanding | None:
    """Struggle rate and weak/not-weak for one pattern, right after logging it.

    Reuses weekly.analyze.analyze() wholesale rather than re-deriving its SQL - it is
    pure SQL/Python, so recomputing it on every log costs nothing. Returns None when
    there is no pattern to look up (enrichment was skipped).
    """
    if pattern is None:
        return None
    analysis = weekly_analyze.analyze(conn, today or date.today())
    row = next((p for p in analysis["patterns"] if p["pattern"] == pattern), None)
    if row is None:
        return None
    return PatternStanding(
        pattern=pattern,
        attempts=row["attempts"],
        struggle_rate=row["struggle_rate"],
        score=row["score"],
        weak=pattern in analysis["weak_patterns"],
        # weak is False on a first attempt because the sample is too small, which
        # would otherwise read as "assessed as solid".
        enough_data=row["attempts"] >= weekly_analyze.WEAK_MIN_ATTEMPTS,
    )


def stats_summary(conn: sqlite3.Connection, today: date | None = None) -> dict:
    """Everything `coach stats` prints and the web home page shows."""
    today = today or date.today()
    total = conn.execute("SELECT COUNT(*) FROM problems").fetchone()[0]
    solved = conn.execute("SELECT COUNT(DISTINCT problem_number) FROM attempts").fetchone()[0]
    attempts = conn.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
    week = conn.execute(
        "SELECT COUNT(*) FROM attempts WHERE date >= ?",
        ((today - timedelta(days=7)).isoformat(),),
    ).fetchone()[0]
    due_count = conn.execute(
        "SELECT COUNT(*) FROM review_state WHERE next_due <= ?", (today.isoformat(),)
    ).fetchone()[0]

    outcomes = [
        {"outcome": r["outcome"], "count": r["n"]}
        for r in conn.execute(
            "SELECT outcome, COUNT(*) AS n FROM attempts GROUP BY outcome ORDER BY n DESC"
        )
    ]
    patterns = [
        {
            "pattern": r["pattern"],
            "attempts": r["attempts"],
            "rough": r["rough"],
            "score": r["score"],
        }
        for r in conn.execute(
            """
            SELECT en.pattern, COUNT(*) AS attempts, SUM(a.outcome != 'clean') AS rough,
                   ps.score
            FROM attempts a
            JOIN solutions s ON s.attempt_id = a.id
            JOIN enrichments en ON en.solution_id = s.id
            LEFT JOIN pattern_scores ps ON ps.pattern = en.pattern
            GROUP BY en.pattern
            ORDER BY attempts DESC, en.pattern
            """
        )
    ]
    off_pattern = [
        {
            "number": r["number"],
            "title": r["title"],
            "difficulty": r["difficulty"],
            "intended_pattern": r["intended_pattern"],
        }
        for r in enrich.off_pattern_problems(conn)
    ]

    progress = {}
    for name, column in curriculum.FLAG_COLUMNS.items():
        in_list = conn.execute(f"SELECT COUNT(*) FROM problems WHERE {column} = 1").fetchone()[0]
        done = conn.execute(
            f"""
            SELECT COUNT(DISTINCT a.problem_number)
            FROM attempts a JOIN problems p ON p.number = a.problem_number
            WHERE p.{column} = 1
            """
        ).fetchone()[0]
        progress[name] = {"done": done, "total": in_list}

    return {
        "catalog": total,
        "solved": solved,
        "attempts": attempts,
        "last_7_days": week,
        "due_today": due_count,
        "outcomes": outcomes,
        "patterns": patterns,
        "off_pattern": off_pattern,
        "curriculum": progress,
    }


def solved_problems(conn: sqlite3.Connection) -> list[dict]:
    """One row per problem with stored code, most recently solved first."""
    rows = conn.execute(
        """
        SELECT p.number, p.title, p.difficulty, p.slug,
               COUNT(s.id) AS solves,
               MAX(s.created_at) AS last_solved,
               (
                   SELECT a.outcome FROM solutions s2
                   JOIN attempts a ON a.id = s2.attempt_id
                   WHERE s2.problem_number = p.number ORDER BY s2.id DESC LIMIT 1
               ) AS last_outcome,
               (
                   SELECT en.pattern FROM solutions s3
                   JOIN enrichments en ON en.solution_id = s3.id
                   WHERE s3.problem_number = p.number ORDER BY s3.id DESC LIMIT 1
               ) AS pattern
        FROM problems p JOIN solutions s ON s.problem_number = p.number
        GROUP BY p.number
        ORDER BY last_solved DESC, p.number
        """
    ).fetchall()
    return [dict(r) for r in rows]


def review_payload(r: review_llm.Review) -> dict:
    """A Review as JSON - the one shape the CLI and the web layer both render."""
    return {
        "verdict": r.verdict,
        "strengths": list(r.strengths),
        "issues": [{"category": i.category, "description": i.description} for i in r.issues],
        "time_complexity": r.time_complexity,
        "space_complexity": r.space_complexity,
        "optimal_time_complexity": r.optimal_time_complexity,
        "better_approach": r.better_approach,
    }


def solution_history(conn: sqlite3.Connection, number: int) -> dict:
    """Every stored solve of one problem, newest first, with its code, tags and review."""
    problem = get_problem(conn, number)
    if problem is None:
        raise ProblemNotFound(number)
    rows = conn.execute(
        """
        SELECT s.id, s.code, s.created_at,
               a.outcome, a.minutes, a.note,
               en.pattern, en.secondary_patterns, en.key_trick,
               en.time_complexity, en.space_complexity
        FROM solutions s
        LEFT JOIN attempts a ON a.id = s.attempt_id
        LEFT JOIN enrichments en ON en.solution_id = s.id
        WHERE s.problem_number = ?
        ORDER BY s.id DESC
        """,
        (number,),
    ).fetchall()
    intended, intended_secondary = problem_canonical(problem)
    solves = []
    for r in rows:
        solve = dict(r)
        solve["secondary_patterns"] = json_list(r["secondary_patterns"])
        solve["also_solvable_with"] = (
            enrich.unused_canonical(
                r["pattern"], solve["secondary_patterns"], intended, intended_secondary
            )
            if r["pattern"]
            else []
        )
        stored = review_llm.load(conn, r["id"])
        solve["review"] = review_payload(stored) if stored else None
        solves.append(solve)
    return {
        "number": number,
        "title": problem["title"],
        "difficulty": problem["difficulty"],
        "slug": problem["slug"],
        "intended_pattern": intended,
        "intended_secondary_patterns": intended_secondary,
        "solves": solves,
    }


def daily_plan(
    conn: sqlite3.Connection, today: date, target: int
) -> list[weekly_plan.PlanItem]:
    """What to solve today, ranked by the same rules as the weekly plan.

    The only difference is the horizon: `lookahead_days=0` counts a review as due
    today rather than any time this week, so a short list is not filled with
    reviews that are not owed yet. Recomputed on every call and stored nowhere -
    a solved problem simply stops appearing.
    """
    analysis = weekly_analyze.analyze(conn, today, lookahead_days=0)
    return weekly_plan.build_plan(conn, analysis, target)


def weekly_report_needed(conn: sqlite3.Connection, today: date) -> bool:
    """True when this ISO week has no report yet.

    Keyed on `generated_at`, like the report filename and the /weekly page's label -
    never `week_start`, which falls in the previous ISO week. Only the newest row
    matters because `generated_at` only moves forward.
    """
    row = conn.execute(
        "SELECT generated_at FROM weekly_runs ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return True
    last = weekly_report.week_key(date.fromisoformat(row["generated_at"]))
    return last != weekly_report.week_key(today)


def run_weekly(
    conn: sqlite3.Connection, today: date, no_llm: bool = False
) -> WeeklyRunResult:
    """Generate the week's report: collect, analyze, narrate, write, record.

    Purely backward-looking - what happened and what it says about the patterns.
    It deliberately plans nothing: `daily_plan` owns what to solve next, and a
    25-problem list frozen into a weekly file went stale the moment one was solved.

    Called by `coach weekly` and, once per ISO week, by `coach today`. The narrative
    is the only paid call and the only optional part: without it the report is still
    written and the run is recorded as degraded.
    """
    week = weekly_collect.collect(conn, today)
    analysis = weekly_analyze.analyze(conn, today)

    note = None
    skipped = None
    if not no_llm:
        try:
            note = weekly_report.narrative(week, analysis)
        except llm.LLMUnavailable as exc:
            skipped = str(exc)

    text = weekly_report.render(week, analysis, note, today)
    path = weekly_report.write(text, today)

    conn.execute(
        """
        INSERT INTO weekly_runs (week_start, generated_at, report_path, stats, degraded, narrative)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            week["start"].isoformat(),
            today.isoformat(),
            str(path.relative_to(config.PROJECT_ROOT)),
            json.dumps(weekly_report.snapshot(week, analysis)),
            int(note is None),
            note,
        ),
    )
    conn.commit()

    return WeeklyRunResult(
        path=path,
        week=weekly_report.week_key(today),
        degraded=note is None,
        narrative_skipped=skipped,
        attempts=len(week["attempts"]),
        due=len(analysis["due"]),
        weak_patterns=analysis["weak_patterns"],
    )


def pattern_counts(conn: sqlite3.Connection) -> list[dict]:
    """Distinct solved problems per pattern — the home page's pattern table.

    A problem counts once under every pattern it was ever practiced with, primary
    or secondary, across all of its solves: solving one problem two ways credits
    both patterns, and re-solving the same way twice still credits it once. The
    inner UNION deduplicates (problem, pattern) pairs before they are counted.
    """
    rows = conn.execute(
        """
        SELECT pattern, COUNT(DISTINCT problem_number) AS solved
        FROM (
            SELECT s.problem_number, en.pattern AS pattern
            FROM solutions s JOIN enrichments en ON en.solution_id = s.id
            UNION
            SELECT s.problem_number, j.value AS pattern
            FROM solutions s
            JOIN enrichments en ON en.solution_id = s.id,
                 json_each(en.secondary_patterns) j
        )
        GROUP BY pattern
        ORDER BY solved DESC, pattern
        """
    ).fetchall()
    return [{"pattern": r["pattern"], "solved": r["solved"]} for r in rows]
