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

from coach import (
    assessment,
    config,
    corrections,
    curriculum,
    embed,
    enrich,
    llm,
    mastery,
    scheduler,
)
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
    attempt_id: int
    solution_id: int
    next_due: date
    counted_as_review: bool  # False when the schedule stayed as it was: early, or a day already counted


@dataclass(frozen=True)
class PracticeDates:
    """When a problem is next owed practice, with its two reasons kept apart.

    `review_due` is SM-2's date for remembering the problem. `correction` is approach
    practice still owed after a solve that used the wrong approach. They answer different
    questions, so neither is folded into the other: `next_practice` is only the earlier.
    """

    review_due: date | None  # None before the first attempt
    correction: corrections.Correction | None
    completed: bool = False  # the attempt just logged completed an outstanding requirement

    @property
    def next_practice(self) -> date | None:
        dates = [self.review_due] if self.review_due else []
        if self.correction:
            dates.append(self.correction.due)
        return min(dates, default=None)


@dataclass(frozen=True)
class Neighbor:
    number: int
    title: str
    difficulty: str
    score: float
    main_patterns: list[str] = field(default_factory=list)
    key_trick: str | None = None


@dataclass(frozen=True)
class EnrichResult:
    """What post-log enrichment produced, including how far it got.

    `skipped` / `embed_skipped` carry the degradation reason: a solve is stored
    whether or not the API answers, so neither is an error.
    """

    main_patterns: list[str] = field(default_factory=list)
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
class ReviewEffect:
    """What saving a review did to its problem's practice schedule.

    The review judges one attempt, but the schedule is a replay of all of them, so
    `latest_attempt_date` travels along: a finding on an old attempt reschedules
    through every solve that came after it.
    """

    finding: assessment.Correctness | None
    attempt_date: date
    latest_attempt_date: date
    next_due_before: date
    next_due: date

    @property
    def rescheduled(self) -> bool:
        return self.next_due != self.next_due_before


@dataclass(frozen=True)
class ReviewResult:
    """A stored or freshly fetched review, plus how far it got.

    `skipped` carries the degradation reason, like `EnrichResult`: no API key means
    no review, never an error. `cached` says whether this cost anything. `effect` is
    set only when a new review was saved - serving a stored one changes nothing.
    """

    review: review_llm.Review | None = None
    cached: bool = False
    skipped: str | None = None
    effect: ReviewEffect | None = None


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
    attempts: list[dict]
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


def update_review_state(conn: sqlite3.Connection, number: int) -> scheduler.ReviewState:
    """Reschedule one problem from every attempt logged against it, and their reviews.

    Replayed from the attempts instead of stepped forward from the stored row: what a
    solve does to the schedule depends on the other solves that day and on a review that
    can arrive days later, and scheduler.replay() is the one owner of that rule. Each
    attempt is graded by assessment.effective_quality() - the grade mastery caps its
    score at - so an unreviewed or untagged attempt counts at its logged outcome.
    """
    rows = conn.execute(
        """
        SELECT a.date, a.outcome, rv.verdict, rv.issues
        FROM attempts a
        LEFT JOIN solutions s ON s.attempt_id = a.id
        LEFT JOIN reviews rv ON rv.solution_id = s.id
        WHERE a.problem_number = ?
        """,
        (number,),
    )
    new = scheduler.replay(
        [
            (
                date.fromisoformat(r["date"]),
                assessment.effective_quality(r["outcome"], r["verdict"], json_list(r["issues"])),
            )
            for r in rows
        ]
    )
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


def rebuild_review_states(conn: sqlite3.Connection) -> int:
    """Reschedule every problem that has an attempt, and say how many.

    A schedule is otherwise recomputed only when its problem is next logged, so this is
    what `coach init` runs to bring schedules stored under an older rule up to date.
    """
    rows = conn.execute("SELECT DISTINCT problem_number FROM attempts").fetchall()
    for row in rows:
        update_review_state(conn, row["problem_number"])
    conn.commit()
    return len(rows)


def stored_review_state(conn: sqlite3.Connection, number: int) -> scheduler.ReviewState | None:
    """The schedule update_review_state() last stored for a problem; None before any attempt."""
    row = conn.execute(
        "SELECT ease, interval_days, next_due, reps, lapses FROM review_state WHERE problem_number = ?",
        (number,),
    ).fetchone()
    if row is None:
        return None
    return scheduler.ReviewState(
        ease=row["ease"],
        interval_days=row["interval_days"],
        next_due=date.fromisoformat(row["next_due"]),
        reps=row["reps"],
        lapses=row["lapses"],
    )


def log_solve(
    conn: sqlite3.Connection,
    number: int,
    outcome: str,
    code: str,
    minutes: int | None = None,
    note: str | None = None,
    today: date | None = None,
) -> LogResult:
    """Store an attempt + solution and reschedule its review.

    Whether the solve counted as a review is read off the schedule itself: every day that
    counts moves reps or lapses, so a replay that leaves the stored state as it was is a
    solve the schedule did not count - early, or on a day already counted.
    """
    problem = get_problem(conn, number)
    if problem is None:
        raise ProblemNotFound(number)
    code = code.strip()
    if not code:
        raise EmptySolution(number)

    today = today or date.today()
    before = stored_review_state(conn, number)
    attempt_id = conn.execute(
        "INSERT INTO attempts (problem_number, date, outcome, minutes, note) VALUES (?, ?, ?, ?, ?)",
        (number, today.isoformat(), outcome, minutes, note),
    ).lastrowid
    solution_id = conn.execute(
        "INSERT INTO solutions (problem_number, attempt_id, code, created_at) VALUES (?, ?, ?, ?)",
        (number, attempt_id, code, today.isoformat()),
    ).lastrowid
    state = update_review_state(conn, number)
    conn.commit()

    return LogResult(
        number=number,
        title=problem["title"],
        outcome=outcome,
        minutes=minutes,
        attempt_id=attempt_id,
        solution_id=solution_id,
        next_due=state.next_due,
        counted_as_review=state != before,
    )


def practice_dates(
    conn: sqlite3.Connection, number: int, logged_attempt: int | None = None
) -> PracticeDates:
    """When one problem is next owed practice: its SM-2 review and any approach practice.

    Pass the attempt just logged to also learn whether it completed approach practice: the
    same history judged without that attempt still owed it, and judged with it owes nothing.
    One load judged twice in memory, so there is no before-and-after snapshot to keep in step.
    """
    stored = stored_review_state(conn, number)
    review_due = stored.next_due if stored else None
    histories = corrections.load(conn, number)
    if not histories:
        return PracticeDates(review_due, correction=None)

    [history] = histories
    correction = corrections.evaluate(history.problem, history.canonical, history.attempts)
    if logged_attempt is None:
        return PracticeDates(review_due, correction)
    earlier = [a for a in history.attempts if a.id != logged_attempt]
    owed_before = corrections.evaluate(history.problem, history.canonical, earlier)
    return PracticeDates(
        review_due, correction, completed=owed_before is not None and correction is None
    )


def neighbor_details(conn: sqlite3.Connection, hits: list[embed.Hit]) -> list[Neighbor]:
    """Attach each hit's title, and the main patterns and trick of the solve that matched.

    Not the problem's latest solve: a problem solved two ways is found through either
    one, and describing it by the other showed an approach the match was not about.
    """
    neighbors = []
    for hit in hits:
        row = conn.execute(
            """
            SELECT p.title, p.difficulty, en.main_patterns, en.key_trick
            FROM solutions s
            JOIN problems p ON p.number = s.problem_number
            JOIN enrichments en ON en.solution_id = s.id
            WHERE s.id = ?
            """,
            (hit.solution_id,),
        ).fetchone()
        neighbors.append(
            Neighbor(
                number=hit.number,
                title=row["title"],
                difficulty=row["difficulty"],
                score=hit.score,
                main_patterns=json_list(row["main_patterns"]),
                key_trick=row["key_trick"],
            )
        )
    return neighbors


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
        main_patterns=list(e.main_patterns),
        secondary_patterns=list(e.secondary_patterns),
        key_trick=e.key_trick,
        intended_pattern=canonical.intended,
        intended_secondary_patterns=canonical.secondary,
        off_pattern=enrich.off_pattern(e.main_patterns, e.secondary_patterns, *canonical),
        also_solvable_with=enrich.unused_canonical(
            e.main_patterns, e.secondary_patterns, *canonical
        ),
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

    card = embed.card_text(problem["title"], tagged.main_patterns, tagged.key_trick, code)
    try:
        vectors = embed.encode([card])
    except embed.EmbeddingsUnavailable as exc:
        return replace(tagged, embed_skipped=str(exc))

    embed.store(conn, solution_id, vectors[0])
    conn.commit()
    hits = embed.search(
        conn, vectors, top_k=3, exclude_problem=problem["number"], patterns=tagged.main_patterns
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
    already reviewed is free and writes nothing. `refresh` forces a new call.

    A new review re-grades the attempt it judges, so the problem is rescheduled in the
    transaction that saves it: a review whose schedule failed to follow would be a
    finding mastery counts and the planner ignores. The model call comes first, holding
    no lock, and the history is replayed after it, so a solve logged meanwhile counts.
    """
    if not refresh:
        stored = review_llm.load(conn, solution_id)
        if stored is not None:
            return ReviewResult(review=stored, cached=True)

    try:
        r = review_llm.review_solution(problem, code)
    except llm.LLMUnavailable as exc:
        return ReviewResult(skipped=str(exc))

    number = problem["number"]
    before = stored_review_state(conn, number)
    with conn:
        review_llm.save(conn, solution_id, r)
        after = update_review_state(conn, number)
    return ReviewResult(
        review=r, effect=review_effect(conn, solution_id, r, before.next_due, after.next_due)
    )


def review_effect(
    conn: sqlite3.Connection,
    solution_id: int,
    r: review_llm.Review,
    next_due_before: date,
    next_due: date,
) -> ReviewEffect:
    """The finding a just-saved review reports, the attempt it judges, and how the date moved."""
    dates = conn.execute(
        """
        SELECT a.date,
               (SELECT MAX(b.date) FROM attempts b WHERE b.problem_number = a.problem_number) AS latest
        FROM solutions s JOIN attempts a ON a.id = s.attempt_id
        WHERE s.id = ?
        """,
        (solution_id,),
    ).fetchone()
    return ReviewEffect(
        finding=assessment.correctness_finding(r.verdict, [i.model_dump() for i in r.issues]),
        attempt_date=date.fromisoformat(dates["date"]),
        latest_attempt_date=date.fromisoformat(dates["latest"]),
        next_due_before=next_due_before,
        next_due=next_due,
    )


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


def pattern_standings(
    conn: sqlite3.Connection, patterns: list[str], today: date | None = None
) -> list[PatternStanding]:
    """Struggle rate and weak/not-weak for each of a solve's main patterns, right after logging.

    Reuses weekly.analyze.analyze() wholesale rather than re-deriving its SQL - it is
    pure SQL/Python, so recomputing it on every log costs nothing, and one analysis
    answers for every pattern. No patterns (enrichment was skipped) means no
    standings, and a pattern with no tagged history yet has nothing to stand on.
    """
    if not patterns:
        return []
    analysis = weekly_analyze.analyze(conn, today or date.today())
    rows = {p["pattern"]: p for p in analysis["patterns"]}
    standings = []
    for pattern in patterns:
        row = rows.get(pattern)
        if row is None:
            continue
        standing = standing_of(analysis, pattern, row["attempts"])
        standings.append(
            PatternStanding(
                pattern=pattern,
                attempts=row["attempts"],
                struggle_rate=row["struggle_rate"],
                score=row["score"],
                weak=standing == "weak",
                enough_data=standing != "too-early",
            )
        )
    return standings


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
                   SELECT en.main_patterns FROM solutions s3
                   JOIN enrichments en ON en.solution_id = s3.id
                   WHERE s3.problem_number = p.number ORDER BY s3.id DESC LIMIT 1
               ) AS main_patterns
        FROM problems p JOIN solutions s ON s.problem_number = p.number
        GROUP BY p.number
        ORDER BY last_solved DESC, MAX(s.id) DESC
        """
    ).fetchall()
    return [{**dict(r), "main_patterns": json_list(r["main_patterns"])} for r in rows]


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
               en.main_patterns, en.secondary_patterns, en.key_trick,
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
        solve["main_patterns"] = json_list(r["main_patterns"])
        solve["secondary_patterns"] = json_list(r["secondary_patterns"])
        solve["also_solvable_with"] = (
            enrich.unused_canonical(
                solve["main_patterns"], solve["secondary_patterns"], intended, intended_secondary
            )
            if solve["main_patterns"]
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
    # show in the table; they just have no pattern to say anything about. A solve
    # with several main patterns was practice of each.
    used = Counter(pattern for r in week["attempts"] for pattern in r["main_patterns"])

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


def pattern_table(conn: sqlite3.Connection) -> list[dict]:
    """The home page's pattern table: one row per pattern a solve led with, most solved first.

    Every column comes from `mastery.pattern_stats`, so problems solved, mastery,
    attempts and not-clean all count the same solves. The table used to join that to
    a second query that also credited each solve's secondary patterns, which listed
    patterns no solve had led with - rows of dashes, and solved counts larger than
    the attempts beside them.
    """
    stats = sorted(
        mastery.pattern_stats(mastery.load_history(conn)),
        key=lambda p: (-p["solved"], p["pattern"]),
    )
    return [
        {
            "pattern": p["pattern"],
            "solved": p["solved"],
            "score": p["score"],
            "attempts": p["attempts"],
            "rough": p["rough"],
        }
        for p in stats
    ]
