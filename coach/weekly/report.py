import json
from datetime import date
from pathlib import Path

from coach import config, llm, mastery
from coach.weekly import analyze

NARRATIVE_PROMPT = """\
You are a direct, supportive LeetCode interview-prep coach. Based on this week's data,
write ONE paragraph (4-6 sentences) diagnosing how the week went and what the student
should work on next, and why. Ground every claim in the attempts and patterns below -
name the problems they actually solved and the patterns that are weak, stale or solved
off-pattern. Do not hand out a list of problems to solve: a separate daily command picks
those. No headers, no lists, no filler praise.

{summary}\
"""


def week_key(today: date) -> str:
    iso = today.isocalendar()
    return f"{iso.year}-{iso.week:02d}"


def review_note(row) -> str:
    """A stored review as one trailing clause, so the narrative can name what broke.

    Already-paid-for judgement: `outcome` is how the solve felt, the review is what
    the code actually did. Empty string when that solve was never reviewed.
    """
    if not row["review_verdict"]:
        return ""
    issues = "; ".join(
        f"{i['category']}: {i['description']}" for i in json.loads(row["review_issues"])
    )
    return f" review={row['review_verdict']}" + (f" ({issues})" if issues else "")


def summarize(week: dict, analysis: dict) -> str:
    """Compact plain-text digest of the week - input for the narrative LLM call."""
    lines = [f"Attempts this week: {len(week['attempts'])} on {week['distinct_problems']} problems"]
    for r in week["attempts"]:
        lines.append(
            f"  {r['date']} #{r['problem_number']} {r['title']} [{r['difficulty']}]"
            f" outcome={r['outcome']} pattern={r['pattern'] or 'untagged'}{review_note(r)}"
        )
    if analysis["weak_patterns"]:
        # Worded from the constants that decide it - this line is the LLM's only
        # definition of "weak", and a hand-written one went stale once already.
        lines.append(
            f"Weak patterns (mastery below {mastery.WEAK_SCORE} over"
            f" {analyze.WEAK_MIN_ATTEMPTS}+ attempts): " + ", ".join(analysis["weak_patterns"])
        )
    if analysis["stale_patterns"]:
        lines.append(
            f"Stale patterns (untouched >{analyze.STALE_DAYS}d): "
            + ", ".join(analysis["stale_patterns"])
        )
    for r in analysis["off_pattern"]:
        lines.append(
            f"Solved off-pattern: #{r['number']} {r['title']} (canonical: {r['intended_pattern']})"
        )
    for name, (done, total) in analysis["curriculum"].items():
        lines.append(f"Curriculum {name}: {done}/{total}")
    lines.append(f"Reviews coming due: {len(analysis['due'])}")
    return "\n".join(lines)


def narrative(week: dict, analysis: dict) -> str:
    return llm.text(NARRATIVE_PROMPT.format(summary=summarize(week, analysis)))


def snapshot(week: dict, analysis: dict) -> dict:
    """Everything render() shows, as JSON - the frozen picture /weekly serves.

    Stored once by `coach weekly` alongside the narrative, so the web page never
    recomputes it and shows exactly what this run saw, not today's live numbers.
    Mirrors render()'s sections one-for-one, rather than a hand-picked summary of
    them, so the two views cannot quietly drift apart the way they already had.
    """
    return {
        "attempts": len(week["attempts"]),
        "distinct_problems": week["distinct_problems"],
        "attempts_detail": [
            {
                "date": r["date"],
                "number": r["problem_number"],
                "title": r["title"],
                "difficulty": r["difficulty"],
                "outcome": r["outcome"],
                "minutes": r["minutes"],
                "pattern": r["pattern"],
            }
            for r in week["attempts"]
        ],
        "patterns": [
            {
                "pattern": p["pattern"],
                "attempts": p["attempts"],
                "struggle_rate": round(p["struggle_rate"], 3),
                "score": round(p["score"], 2) if p["score"] is not None else None,
                "weak": p["pattern"] in analysis["weak_patterns"],
                "stale": p["pattern"] in analysis["stale_patterns"],
            }
            for p in analysis["patterns"]
        ],
        "weak_patterns": analysis["weak_patterns"],
        "stale_patterns": analysis["stale_patterns"],
        "off_pattern": [
            {"number": r["number"], "title": r["title"], "intended_pattern": r["intended_pattern"]}
            for r in analysis["off_pattern"]
        ],
        "curriculum": {name: {"done": d, "total": t} for name, (d, t) in analysis["curriculum"].items()},
        "due": len(analysis["due"]),
    }


def render(week: dict, analysis: dict, note: str | None, today: date) -> str:
    lines = [f"# Weekly report — {week_key(today)}", ""]
    lines.append(f"Window: {week['start'].isoformat()} to {week['end'].isoformat()}"
                 f" · generated {today.isoformat()}")
    lines.append("")

    lines.append("## This week")
    lines.append("")
    if week["attempts"]:
        lines.append(f"{len(week['attempts'])} attempt(s) on {week['distinct_problems']} problem(s).")
        lines.append("")
        lines.append("| Date | Problem | Difficulty | Outcome | Minutes | Pattern |")
        lines.append("|---|---|---|---|---|---|")
        for r in week["attempts"]:
            lines.append(
                f"| {r['date']} | #{r['problem_number']} {r['title']} | {r['difficulty']}"
                f" | {r['outcome']} | {r['minutes'] or ''} | {r['pattern'] or ''} |"
            )
    else:
        lines.append("**No attempts logged this week.** Run `coach today` to pick the"
                     " next few problems up again.")
    lines.append("")

    if analysis["patterns"]:
        lines.append("## Patterns (all-time)")
        lines.append("")
        lines.append("| Pattern | Attempts | Struggle rate | Flags |")
        lines.append("|---|---|---|---|")
        for p in analysis["patterns"]:
            flags = []
            if p["pattern"] in analysis["weak_patterns"]:
                flags.append("weak")
            if p["pattern"] in analysis["stale_patterns"]:
                flags.append("stale")
            lines.append(
                f"| {p['pattern']} | {p['attempts']} | {p['struggle_rate']:.0%}"
                f" | {', '.join(flags)} |"
            )
        lines.append("")

    if analysis["off_pattern"]:
        lines.append("## Solved off-pattern")
        lines.append("")
        for r in analysis["off_pattern"]:
            lines.append(f"- #{r['number']} {r['title']} — canonical approach is"
                         f" **{r['intended_pattern']}**, never used")
        lines.append("")

    lines.append("## Where you stand")
    lines.append("")
    for name, (done, total) in analysis["curriculum"].items():
        lines.append(f"- {name}: {done}/{total}")
    lines.append(f"- reviews coming due: {len(analysis['due'])}")
    lines.append("")

    lines.append("## Coach's note")
    lines.append("")
    lines.append(note if note else "_LLM unavailable this week — report written without narrative._")
    lines.append("")
    lines.append("_What to solve next is picked daily: run `coach today`._")
    lines.append("")
    return "\n".join(lines)


def write(text: str, today: date) -> Path:
    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = config.REPORTS_DIR / f"{week_key(today)}.md"
    path.write_text(text)
    return path
