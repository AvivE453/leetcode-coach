# Service, API and pages

How a request reaches the logic: the service layer, the JSON API over it, the CLI beside it, and
the pages that call the API.

## Three thin layers over the logic

```text
browser  -> coach/web/app.py (FastAPI, JSON) \
                                              -> coach/service.py -> logic -> SQLite
terminal -> coach/cli.py (typer)             /
```

- [coach/service.py](../coach/service.py) holds every request's work. It takes a connection and
  plain arguments, returns a dataclass (`LogResult`, `DailyPlan`, ...), and never prints, so it
  does not know whether a page or a terminal asked.
- [coach/web/app.py](../coach/web/app.py) is a thin JSON translation: each endpoint opens a
  connection, calls one or two service functions, and turns the result into a dict, through small
  payload helpers (`practice_payload`, `plan_item_payload`) so every page that shows the same
  thing gets the same shape. A service error (`ProblemNotFound`, `SolveNotFound`) becomes an HTTP
  404 here; the service knows nothing of HTTP.
- [coach/cli.py](../coach/cli.py) keeps only the jobs with no page: `init`, `enrich`, `similar`.

Enrichment shows why there is one implementation: logging a solve and the `coach enrich`
backfill both run `service.tag_solution_now()`, and differ only in how they embed, one card per
solve or one batch at the end, so the two cannot drift into tagging differently.

Every daily feature used to exist three times, as a service function, a CLI printer and a page,
and once the page could do everything the printer did, nobody read the printer; a change had to
land in three places. The printers were retired, and a CLI command does not come back for
anything that has a page.

**Input is checked at the boundary.** A request body is a Pydantic class (`LogRequest`: a
positive number, one of the four outcomes, code, non-negative minutes), and a path parameter is
converted by its type hint, so FastAPI answers 422 before any of our code runs. Past the
boundary the code trusts what it was given.

**Reading is free.** Every `GET` only reads: none writes and none calls a model. The three
writes are each an explicit action: `POST /api/log` (log a solve), `POST
/api/solutions/{number}/review` (buy or fetch a review; `POST` even when one is stored, because
it can spend money and write), and `DELETE /api/solutions/{number}/{solution_id}` (delete one
solve).

## One connection per request, opened inside the endpoint

Every endpoint starts with `with open_db() as conn:`, a context manager that opens a connection
(`db.connect()`) and closes it when the request ends, even after an error. It is not the
transaction: `with conn:` inside a service function commits or rolls back a write but leaves the
connection open ([database.md](database.md#connections-and-transactions)), so a request needs
both.

The connection is deliberately not a FastAPI dependency (`Depends`). The endpoints are plain
`def` functions, which FastAPI runs in a threadpool, and a plain dependency runs there as a
separate task, possibly on another thread. Python's `sqlite3` refuses a connection used from a
thread other than the one that opened it, so under concurrent requests (Home loads
`/api/stats` and `/api/patterns` at once) a shared dependency's connection would cross threads
and the request would 500. Opened inside the endpoint, it is created and used on one thread.
`test_endpoints_survive_parallel_requests` sends 18 requests on 8 threads and requires every one
to answer 200.

There is no connection pool: opening SQLite is opening a file, with no server, network or login
to amortize, and a fresh connection per request means no request inherits another's state.

## The pages

Each page is a hand-written HTML file in [coach/web/static/](../coach/web/static/) with its own
script (`plan.html` and `plan.js`, and so on), served by FastAPI as they are. There is no
framework, no npm and no build step: five pages for one user, each rendering the JSON of one
endpoint, do not need one.

The HTML is a skeleton of empty elements with ids, and the script fills them: it `await`s
`getJSON("/api/...")` and renders, and any failure (including a non-2xx answer, which `getJSON`
throws on) is shown at the top of the page. `dom.js` holds the shared helpers (`el`, `getJSON`,
`patternBadges`, ...) as plain globals, since there are no modules, so every page loads it
before its own script.

**Text, never HTML.** `el(tag, {text: ...})` sets `textContent`. Solutions shows code exactly as
it was pasted, and through `innerHTML` a `<` in it would be parsed as a tag, and a pasted
`<img onerror=...>` would run: an XSS hole. User code is rendered with `textContent` only.

**A page and its script are one unit.** The script reaches into the markup by id, and the markup
never names its script, so renaming an id in one file and not the other fails nowhere:
`getElementById` returns null and the page breaks where it is first used. It happened: `weekly.js`
reached for ids `weekly.html` had dropped, the null landed inside the catch block meant to report
the failure, and the page sat on its loading text while the server logged a 200. Two things
guard it:

- `tests/test_static_pages.py` collects every `getElementById("...")` of each script and checks
  the id is declared by the page that loads it, and that every lookup is a string literal the
  check can see.
- Every page and static file is served with `Cache-Control: no-cache` (revalidate, not
  re-download: an unchanged file is a 304), so the browser never pairs a cached script with
  fresh markup.

**Links between pages carry `?number=N`**: a Daily Plan problem opens `/log?number=N` with its
number filled in, and the log result's "Go to review" opens `/solutions?number=N`. The link is
built by one script and read by another, so only the browser tests (`tests/browser/`) catch a
mismatch.

Empty states are worded from numbers the API serves (`thresholds`: `WEAK_SCORE`,
`WEAK_MIN_PROBLEMS`, `STALE_DAYS`), not restated in the scripts, so changing a constant changes
the sentence. The static files are read from disk on every request, while a change to `app.py`
needs `coach-web` restarted, so a refreshed page can show a button whose route the running
server does not have yet (`{"detail":"Not Found"}`).

## One solve, from the click to every page

Following one solve: Two Sum is under the Daily Plan's "Time to revisit", and is solved clean
with a hash map.

1. **The plan links to the log page.** The problem's name is `/log?number=1`; `log.js` fills the
   number in and focuses the code field. Code pasted, `clean` picked, the button counts dots
   while the model works.
2. **The request.** `POST /api/log` with `{number, outcome, code}`. `LogRequest` checks the body
   (422), and `api_log` checks the problem exists (404) and the code is not empty (400).
3. **Three writes, each its own transaction**, the solve first:
   - `service.log_solve` inserts the solve (with `due_when_logged`) and replays the problem's
     review schedule ([logic.md](logic.md#the-review-schedule)). Commit.
   - `service.tag_solution_now` calls the language model outside any transaction, then saves the
     tags, discards the old vector and merges the accepted set ([llm.md](llm.md)). Commit.
   - `service.enrich_solution_now` embeds the new card locally and stores the vector
     ([search.md](search.md)). Commit.

   A model that fails stops after the first commit (`skipped`); a missing embedding model after
   the second (`embedding_skipped`). Either way the solve and its schedule stand, and
   `coach enrich` fills in the rest.
4. **Reads, after the writes.** The three nearest solves sharing a main pattern; each main
   pattern's standing (`pattern_standings`, through `analyze()` over `history.load()`); and
   whether this solve completed approach practice (`practice_dates`, judging the history with
   and without it).
5. **The log page renders the one JSON answer**: the next review date and whether the solve
   counted as one, the tags and trick, an off-pattern warning or an "also solvable with" note,
   the neighbors, the standings, and a "Go to review" link to `/solutions?number=1`.
6. **Every other page recomputes on open.** Nothing is pushed: Home's counts and pattern table,
   the Daily Plan (where Two Sum is simply no longer due, so it is not listed), Solutions (the
   new solve, and a Review button that, on a bug, re-grades the attempt and replays the schedule
   in one transaction), and the Weekly Review (the solve in the week, `hashmap`'s delta moved).

Three rules show in it: small writes, each whole, with the solve itself first; the model never
called inside a transaction; and everything recomputed on read, so no page can know about a
solve another page does not.

## Pull, don't push

Nothing runs unattended: no cron job, no systemd timer, no scheduled writer. Every page computes
what it shows from the database when it is opened, in a few milliseconds, so there is nothing
left to schedule. The project arrived at this twice, through a GitHub Actions cron and then a
systemd timer that wrote a weekly report, and each time the stored result was the problem: it
went stale, or was overwritten by a worse one.
