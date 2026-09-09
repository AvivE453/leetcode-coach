# leetcode-coach

A personal interview-prep coach that closes the loop on LeetCode practice: it remembers
what you solved and *how*, tells you when to re-solve it, retrieves your own past
solutions by algorithmic pattern, and plans each day around your measured weaknesses.

Solving 20–30 problems a week leaks. There is no record of which patterns are strong, no
signal when a problem was "solved" without learning what it teaches, and no schedule that
brings it back before you forget it. This fixes that.

## Install

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --extra embed          # omit --extra embed to skip torch (no local embeddings)
uv sync --extra web            # optional: FastAPI + uvicorn for the browser UI
cp .env.example .env           # then add your Anthropic API key; .env is gitignored
uv run coach init              # download the problem catalog, create the database
```

## Use

```bash
uv run coach today                            # start here: what to solve today
uv run coach log 1 --outcome clean --time 8   # paste your solution, then Ctrl+D
```

| Command | What it gives you |
|---|---|
| `coach today` | **The daily entry point.** Today's problems, in priority order |
| `coach log <n>` | Paste a solution → stores it, tags the pattern, embeds it, schedules the review, shows similar past solves, and flags the solve if you used the wrong approach |
| `coach due` | What to re-solve today, by spaced repetition |
| `coach similar <n>` / `--paste` | Your five most similar past solutions, by *algorithmic pattern* rather than text |
| `coach review <n>` | Structured feedback on a stored solution: what it got right, complexity, bugs, edge cases, better approach. Stored after the first run, so looking again is free |
| `coach stats` | Pattern coverage, mastery scores, struggle rates, off-pattern solves, curriculum progress |
| `coach weekly` | The last seven days: every solve, and whether each pattern you used is going well, needs work, or has too little history to call |
| `coach enrich` | Backfills tags and embeddings for anything logged while offline |

A logged solve is never lost: with no API key it still saves, and `coach enrich` fills in
the tags later.

## Web UI

```bash
uv run coach-web        # http://127.0.0.1:8000
```

Four pages over the same data — **Home** (progress, patterns practised, and a form to log
a solve), **Solutions** (every solve with its code and review), **Daily Plan** (the
browser version of `coach today`), and **Weekly Review** (this week, recomputed live).
Opening a page never spends money.

It binds to localhost and has no authentication, so keep it there.
`COACH_WEB_HOST` / `COACH_WEB_PORT` move it.

## Notes

`COACH_DB=/tmp/scratch.db` points any command, `coach-web` included, at a throwaway
database.

Your database starts empty and grows from your first `coach log`. `data/coach.db` is
gitignored on purpose — it holds your practice history, not the tool — so it is the only
copy of that history, and nothing in git backs it up for you.

```bash
uv run pytest          # every LLM call mocked, API key stripped
uv run ruff check .
```

`tests/browser/` loads all four pages in a real Chromium and fails if any script
throws or leaves its page on the loading text — the one failure the other suites
cannot see, since they never execute the JavaScript. It starts `coach-web` itself
on a temporary database, so it needs no setup beyond the browser binary, which is
a separate download from `uv sync`:

```bash
uv run playwright install chromium
```

Without it that test skips and the rest of the suite still passes.

## How it works

Everything the LLM does here is **measured**, not assumed: review feedback catches 97% of
planted flaws with a 0% false-positive rate, against ground truth produced by *executing*
mutated solutions rather than by opinion.

The architecture, the design decisions behind it, and the full eval methodology are in
**[docs/DESIGN.md](docs/DESIGN.md)**.
