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
cp .env.example .env           # then add your Anthropic API key; .env is gitignored
uv run coach init              # download the problem catalog, create the database
```

## Use

```bash
uv run coach-web        # http://127.0.0.1:8000
```

Day-to-day use happens in the browser, on four pages over the same data:

| Page | What it gives you |
|---|---|
| **Daily Plan** | **Start here.** Today's problems, in priority order: reviews due by spaced repetition, then off-pattern re-solves, weak-pattern picks, and curriculum progression |
| **Home** | Progress, every pattern you have practised with its mastery score, and **I solved a question** — paste a solution and it is stored, tagged by pattern, embedded, scheduled for review, compared with similar past solves, and flagged if you used the wrong approach |
| **Solutions** | Every solve with its code, searchable by number or name, and structured feedback on any of them: what it got right, complexity, bugs, edge cases, a better approach. Stored after the first run, so looking again is free |
| **Weekly Review** | The last seven days: every solve, and whether each pattern you used is going well, needs work, or has too little history to call |

Opening a page never spends money. The server binds to localhost and has no
authentication, so keep it there; `COACH_WEB_HOST` / `COACH_WEB_PORT` move it.

Three jobs have no page and stay on the command line:

| Command | What it gives you |
|---|---|
| `coach init` | Creates the database and loads the problem catalog; also rebuilds the mastery scores |
| `coach enrich` | Backfills tags and embeddings for anything logged while offline |
| `coach similar <n>` / `--paste` | Your five most similar past solutions, by *algorithmic pattern* rather than text |

A logged solve is never lost: with no API key it still saves, and `coach enrich` fills in
the tags later.

## Notes

`COACH_DB=/tmp/scratch.db` points any command, `coach-web` included, at a throwaway
database.

Your database starts empty and grows from your first logged solve. `data/coach.db` is
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
