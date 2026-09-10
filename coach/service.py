"""Logic behind the web UI, and behind the few CLI commands that remain.

Everything here is pure-ish: it takes a connection, touches the database, and
returns data. No printing, no typer, no HTTP. `coach/web/app.py` serialises these
to JSON; `coach/cli.py` wraps the handful it still needs in `typer.echo` calls.
"""

import json
import sqlite3
from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import date, timedelta

from coach import config, curriculum, embed, enrich, llm, mastery, scheduler
from coach import review as review_llm
from coach.weekly import analyze as weekly_analyze
from coach.weekly import collect as weekly_collect
from coach.weekly import plan as weekly_plan


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
class WeekPattern:
    """One pattern practiced this week, and how it is going.

    `score_before` is the same mastery number folded over this pattern's history
    up to the start of the window, so `delta` says whether the week moved it.
    """

    pattern: str
    attempts_week: int
    attempts_total: int
    score: float
    score_before: float | None
    standing: str

    @property
    def delta(self) -> float | None:
        """How much mastery moved this week. None for a pattern first practiced in it."""
        if self.score_before is None:
            return None
        return self.score - self.score_before


@dataclass(frozen=True)
class WeeklyReview:
    """The last seven days: what was solved, and what each pattern used says.

    Computed on demand and stored nowhere, so logging a solve changes it
    immediately - the report file and the frozen snapshot it replaced went stale
    the moment the next problem was solved.
    """

    start: date
    end: date
    attempts: list[sqlite3.Row]
    distinct_problems: int
    patterns: list[WeekPattern]


@dataclass(frozen=True)
class DailyPlan:
    """Today's ranked list, plus the analysis that ranked it.

    The two travel together because the horizon that produced them is a property
    of the pair: reading `items` against a differently-analyzed `analysis` is the
    bug this replaced.
    """

    items: list[weekly_plan.PlanItem]
    analysis: dict


@dataclass(frozen=True)
class PatternStanding:
    """Where a pattern currently stands, per the existing weekly analyze() aggregates."""

    pattern: str
    attempts: int
    struggle_rate: float
    score: float
    weak: bool
    enough_data: bool


def get_problem(conn: sqlite3.Connection, number: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM problems WHERE number = ?", (number,)).fetchone()


def json_list(raw: str | None) -> list[str]:
    return json.loads(raw) if raw else []


def problem_canonical(problem) -> enrich.Canonical:
    """A problem row's canonical approaches: (intended, intended_secondary).

    Tolerates a row from before the column existed, so a caller holding an old
    query result still gets the single-pattern behaviour rather than an error.
    """
    try:
        secondary = json_list(problem["intended_secondary_patterns"])
    except (IndexError, KeyError):
        secondary = []
    return enrich.Canonical(problem["intended_pattern"], secondary)


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


def tag_solution_now(
    conn: sqlite3.Connection, solution_id: int, problem: sqlite3.Row, code: str
) -> EnrichResult:
    """Tag one stored solution and judge it against its problem's canonical set.

    The one enrichment workflow: logging a solve runs it through enrich_solution_now(),
    and `coach enrich` runs it per solution before embedding everything in one batch.
    It never embeds, so `neighbors` and `embed_skipped` on its result mean "not
    attempted". No API key -> `skipped`, and the stored solve is untouched.
    """
    try:
        e = enrich.enrich_solution(problem, code)
    except llm.LLMUnavailable as exc:
        return EnrichResult(skipped=str(exc))

    enrich.save(conn, solution_id, e)
    canonical = enrich.save_intended(
        conn, problem["number"], e.intended_pattern, list(e.intended_secondary_patterns)
    )
    conn.commit()

    # Two signals off one free set comparison: off_pattern is the sharp one (no
    # canonical approach used at all), also_solvable_with is informational.
    return EnrichResult(
        pattern=e.pattern,
        secondary_patterns=list(e.secondary_patterns),
        key_trick=e.key_trick,
        intended_pattern=canonical.intended,
        intended_secondary_patterns=canonical.secondary,
        off_pattern=enrich.off_pattern(e.pattern, e.secondary_patterns, *canonical),
        also_solvable_with=enrich.unused_canonical(e.pattern, e.secondary_patterns, *canonical),
    )


def enrich_solution_now(
    conn: sqlite3.Connection, solution_id: int, problem: sqlite3.Row, code: str
) -> EnrichResult:
    """Tag the solution, embed its card, and find similar solves.

    Degrades in two steps: no API key -> `skipped`; no sentence-transformers ->
    `embed_skipped`. Both leave the stored solve untouched.
    """
    tagged = tag_solution_now(conn, solution_id, problem, code)
    if tagged.skipped:
        return tagged

    card = embed.card_text(problem["title"], tagged.pattern, tagged.key_trick, code)
    try:
        vector = embed.encode([card])[0]
    except embed.EmbeddingsUnavailable as exc:
        return replace(tagged, embed_skipped=str(exc))

    embed.store(conn, solution_id, vector)
    conn.commit()
    hits = embed.search(
        conn, vector, top_k=3, exclude_problem=problem["number"], pattern=tagged.pattern
    )
    return replace(tagged, neighbors=neighbor_details(conn, hits))


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
    return ReviewResult(review=r)


def standing_of(analysis: dict, pattern: str, attempts: int) -> str:
    """One pattern's verdict as a word: too-early, weak, or on-track.

    The single owner of that reading, shared by the standing note shown after logging
    a solve and by the weekly review. `weak` is only ever membership in analysis["weak_patterns"] -
    the threshold itself lives in mastery.is_weak() and is applied once, by analyze().

    Too small a sample to call weak is also too small to call solid, so below
    WEAK_MIN_ATTEMPTS the honest answer is "too-early" rather than a guess.
    """
    if attempts < mastery.WEAK_MIN_ATTEMPTS:
        return "too-early"
    return "weak" if pattern in analysis["weak_patterns"] else "on-track"


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
    standing = standing_of(analysis, pattern, row["attempts"])
    return PatternStanding(
        pattern=pattern,
        attempts=row["attempts"],
        struggle_rate=row["struggle_rate"],
        score=row["score"],
        weak=standing == "weak",
        enough_data=standing != "too-early",
    )


def stats_summary(conn: sqlite3.Connection, today: date | None = None) -> dict:
    """The home page's progress numbers: counts, reviews due, outcomes, curriculum.

    Per-pattern practice is not here - the pattern table reads it from pattern_table().
    """
    today = today or date.today()
    total = conn.execute("SELECT COUNT(*) FROM problems").fetchone()[0]
    solved = conn.execute("SELECT COUNT(DISTINCT problem_number) FROM attempts").fetchone()[0]
    attempts = conn.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
    # The same window the weekly report collects, not a second definition of it:
    # `days=7` counted today and the seven days before it - eight - so the home
    # page said 8 where the report said 7 for the same solves.
    week = conn.execute(
        "SELECT COUNT(*) FROM attempts WHERE date >= ?",
        ((today - timedelta(days=weekly_collect.WINDOW_DAYS - 1)).isoformat(),),
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

    return {
        "catalog": total,
        "solved": solved,
        "attempts": attempts,
        "last_7_days": week,
        "due_today": due_count,
        "outcomes": outcomes,
        "curriculum": curriculum.progress(conn),
    }


def solved_problems(conn: sqlite3.Connection) -> list[dict]:
    """One row per problem with stored code, the last one logged first.

    `created_at` is a date, so solves from the same day tie on it. `MAX(s.id)`
    breaks the tie in logging order - the problem number used to, which listed
    #1 above a #15 logged after it.
    """
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
        ORDER BY last_solved DESC, MAX(s.id) DESC
        """
    ).fetchall()
    return [dict(r) for r in rows]


def matches_problem(problem: dict, query: str) -> bool:
    """The search rule: a number that starts with the query, or a title containing it."""
    return str(problem["number"]).startswith(query) or query.casefold() in problem["title"].casefold()


def solutions_listing(
    conn: sqlite3.Connection, query: str = "", recent: int = config.RECENT_SOLUTIONS
) -> dict:
    """What /solutions shows: the `recent` last-logged problems, or every match for `query`.

    Matches are not capped - a search asks for all of them. The totals always count
    everything, so the page can say "10 of 42"; summing the shown rows would quietly
    shrink with the cap. Filtered in Python rather than with LIKE: one readable rule,
    no `%`/`_` escaping, over a few hundred rows already fetched.
    """
    rows = solved_problems(conn)
    query = query.strip()
    shown = [r for r in rows if matches_problem(r, query)] if query else rows[:recent]
    return {
        "problems": shown,
        "query": query,
        "total_problems": len(rows),
        "total_solves": sum(r["solves"] for r in rows),
    }


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


def daily_plan(conn: sqlite3.Connection, today: date, target: int) -> DailyPlan:
    """What to solve today, ranked by the same rules as the weekly plan.

    The only difference is the horizon: `lookahead_days=0` counts a review as due
    today rather than any time this week, so a short list is not filled with
    reviews that are not owed yet. Recomputed on every call and stored nowhere -
    a solved problem simply stops appearing.

    Returns the analysis alongside the list because /api/plan needs both, and
    composing them itself is how it ended up with its own copy of the horizon -
    which then had to be fixed twice on the day the daily plan landed.
    """
    analysis = weekly_analyze.analyze(conn, today, lookahead_days=0)
    return DailyPlan(items=weekly_plan.build_plan(conn, analysis, target), analysis=analysis)


# Worst first: the patterns needing work are what the week is read for, and
# nothing can be said yet about the ones still under WEAK_MIN_ATTEMPTS.
STANDING_ORDER = {"weak": 0, "on-track": 1, "too-early": 2}


def weekly_review(conn: sqlite3.Connection, today: date | None = None) -> WeeklyReview:
    """The last seven days: every solve, and every pattern those solves used.

    Purely backward-looking and entirely free - pure SQL, no LLM, no writes, so it
    can be recomputed on every CLI run and every page load. A pattern is listed if
    it was practiced inside the window, however long ago it was first picked up;
    its standing and mastery are all-time, because a week of practice is not enough
    history to judge a pattern on.
    """
    today = today or date.today()
    week = weekly_collect.collect(conn, today)
    history = mastery.load_history(conn)
    analysis = weekly_analyze.analyze(conn, today, history=history)
    # The same statistics over the same loaded history, cut at the start of the
    # window - so `delta` compares two numbers computed the one way.
    earlier = [a for a in history if a.day < week["start"]]
    score_before = {p["pattern"]: p["score"] for p in mastery.pattern_stats(earlier)}

    all_time = {p["pattern"]: p for p in analysis["patterns"]}
    # Untagged solves (enrichment was skipped) still count as attempts and still
    # show in the table; they just have no pattern to say anything about.
    used = Counter(r["pattern"] for r in week["attempts"] if r["pattern"])

    patterns = [
        WeekPattern(
            pattern=name,
            attempts_week=count,
            attempts_total=all_time[name]["attempts"],
            score=all_time[name]["score"],
            score_before=score_before.get(name),
            standing=standing_of(analysis, name, all_time[name]["attempts"]),
        )
        for name, count in used.items()
    ]
    patterns.sort(key=lambda p: (STANDING_ORDER[p.standing], p.pattern))

    return WeeklyReview(
        start=week["start"],
        end=week["end"],
        attempts=week["attempts"],
        distinct_problems=week["distinct_problems"],
        patterns=patterns,
    )


def pattern_counts(conn: sqlite3.Connection) -> list[dict]:
    """Distinct solved problems per pattern — the coverage half of `pattern_table`.

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


def pattern_table(conn: sqlite3.Connection) -> list[dict]:
    """The home page's pattern table: coverage and practice, one row per pattern.

    Composed from the two definitions that already exist rather than a third query:
    which patterns each problem credits (`pattern_counts`) and how each pattern is
    going (`mastery.pattern_stats`). Practice is measured on the pattern a solve led
    with, so a pattern only ever credited as a secondary has no practice row - its
    score/attempts/rough are None, not a zero that would read as practiced-and-failed.
    """
    practice = {p["pattern"]: p for p in mastery.pattern_stats(mastery.load_history(conn))}
    table = []
    for row in pattern_counts(conn):
        p = practice.get(row["pattern"], {})
        table.append(
            {**row, "score": p.get("score"), "attempts": p.get("attempts"), "rough": p.get("rough")}
        )
    return table
