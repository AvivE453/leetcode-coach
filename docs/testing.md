# Testing

How the coach is tested: what each kind of test checks, how a test is kept off the real
database and the paid APIs, the tests that exist only to catch two copies drifting apart, and
the browser tests.

## The shape of the suite

`uv run pytest` runs 459 tests in [tests/](../tests/) in about a minute and a half, with no
network and no keys. Two more, in [tests/browser/](../tests/browser/), drive a real browser.
They follow the code's layers, bottom up:

- **Pure logic** (`test_scheduler.py`, `test_mastery.py`, `test_corrections.py`,
  `test_assessment.py`, `test_history.py`): a function called with hand-built attempts, no
  database. This is where the rules live: the 7/14/3-day intervals, the weak line, approach
  practice closing only on a success.
- **The service** (`test_service.py`, the largest): a fresh SQLite database in a temporary
  directory, solves stored in it, and `service.py` called directly. This sees what pure logic
  cannot: a write saved whole, a delete that removes the children first, a review that replays
  the schedule.
- **The API** (`test_web.py`): FastAPI's `TestClient`, which sends HTTP requests to the app in
  the same process without opening a port. Status codes, JSON shapes, and the parallel-requests
  test of [web.md](web.md#one-connection-per-request-opened-inside-the-endpoint).
- **Seams** (`test_vocabulary.py`, `test_static_pages.py`): no code is run; files are read to
  check that two places that must agree do (below).
- **The browser** (`tests/browser/`): a real server and a real Chromium (below).

The eval harness has its own tests (`test_oracle.py`, `test_controls.py`, `test_evals_cache.py`,
`test_evals_report.py`), described with the evals.

A test moves up a layer only when what it checks cannot be seen from below: a whole transaction
needs a database, a status code needs HTTP, a script that never ran needs a browser. Lower tests
are faster and say exactly which rule broke, so most tests are low, and there are two browser
tests, because a browser costs about a hundred unit tests.

**Numbers worked by hand.** `test_mastery.py::test_scoring_behavior_is_pinned` builds one history
whose per-solve scores are worked out in its docstring, then checks the same folded scores in
every reader of mastery: `analyze()`, Home's pattern table and the Weekly Review. It catches an
unintended change to the formula, and one reader starting to compute differently from the
others. When the constants change on purpose, the numbers are reworked by hand, which is also
when to check the history still tests what it was built for.

**No CI.** Nothing runs the suite on a push; it is run by hand before a commit. That works for
one developer, and means a commit made without running it can break `master` unnoticed.

## Isolation: never the real database, never a paid API

A test must never touch `data/coach.db`, the only copy of the history, or call an API that
costs money. Both are kept out in layers, with two pytest tools: a *fixture* is a function that
prepares something for a test (a test asks for one by naming it as a parameter; `tmp_path` gives
each test its own empty directory), and `monkeypatch` replaces an environment variable, a module
attribute or a global for the length of one test and restores it afterwards.

**A scratch database.** Every test that needs a database goes through
[conftest.py](../tests/conftest.py)'s `seed_db`, which points `config.DB_PATH` at a file in
`tmp_path`, creates the schema and seeds a catalog. Everything that opens the database, endpoints
included, goes through `db.connect()` and so opens that file. The browser tests run a separate
server process, where `monkeypatch` cannot reach, so they hand it `COACH_DB` pointing at a
temporary directory and build the database with `coach init`.

**No keys, whatever a test forgets.** Two `autouse` fixtures run before every test: `no_api_key`
deletes both API keys from the environment (`config.py` loads `.env` at import, so the real ones
are there), and `no_catalog_fetch` replaces the LeetCode statement fetch. Without a key,
`llm._complete` raises `LLMUnavailable` before sending anything, so even a test that forgot to
replace the model gets `skipped`, not a bill. A test that reloads `config` re-runs `load_env()`,
which would bring the real keys back, so it must set fake ones for both first (`load_env` uses
`setdefault` and never overwrites a variable that exists).

**Replace at the right seam.** A test that needs a model's answer replaces it explicitly:
`test_web.py`'s `enriched` swaps `llm.parse` for a fixed `Enrichment` and `embed.encode` for a
fixed vector, so logging runs end to end with no network and no `torch`. The seam is chosen above
the code under test, never inside it. `test_llm.py` tests `llm.py` itself, so it keeps the real
OpenAI SDK and replaces only the network (`openrouter_answering`: an `httpx.MockTransport` that
answers a chosen body), because the bugs it exists for live in the SDK parsing a raw answer.
`fake_sentence_transformers` does the same for the embedding model, putting a stand-in package
in `sys.modules` so `embed.encode`'s real load, and its `OSError` handling, run without a
download.

**One copy of each insert.** Tests that build history by hand use conftest's `store_solution`
and `tag_solution`, never their own `INSERT`, so a new column is one edit, not fifty.

## Seam tests: two copies that cannot import each other

Some values must be the same in places that cannot share a definition, because they are
different languages. The four outcomes are declared four times: a `Literal` on `LogRequest`
(Pydantic), a `CHECK` clause on `solutions` (SQL), `scheduler.QUALITY` (Python) and the log
form's radio buttons (HTML). SQL cannot import a Python constant, and HTML cannot import
anything, so the copies exist by necessity, and the seam between them is where a change to one
is forgotten in another with nothing failing. Each pair has a test that says what drifting would
break ([tests/test_vocabulary.py](../tests/test_vocabulary.py)): an outcome the API accepts but
`QUALITY` lacks raises `KeyError` on log; one the form offers but the API rejects is a 422 after
the solution is typed in; one the `CHECK` rejects fails at `INSERT`. The same file keeps the
planner's `PATTERN_TO_TAG` keys a subset of the pattern vocabulary.

[tests/test_static_pages.py](../tests/test_static_pages.py) does the same for the pages: every
id a script looks up is declared by the page that loads it, every lookup is a string literal the
check can see, `dom.js` loads before the page's own script, every `aria-*` reference points at an
id that exists, and every `[name=...]` a script queries is a field of its form. The pages are
discovered with a glob, so a new page is covered the day it is added.

Two rules make these tests trustworthy:

- **Nothing shares code with what it checks.** Each copy is read the way it is written, text
  against text; a test that imported the list from the code would check the code against
  itself.
- **Every check proves it matched something.** A subset check over nothing passes, so a pattern
  that silently stopped matching (a changed quote style, say) would pass forever. Each check is
  paired with an assertion on the number of matches, and
  `test_the_page_scan_finds_the_pages_and_their_scripts` exists only to fail when the scan finds
  fewer pages, scripts or lookups than are there.

## Browser tests

Every other test leaves the JavaScript unrun: `test_web.py` asserts on JSON, and
`test_static_pages.py` reads the scripts as text. A script that throws on its first line would
leave every page blank with the whole suite green, and a script that reads a field the JSON does
not have does not even throw, because a missing key in JavaScript is `undefined`. So
[tests/browser/](../tests/browser/) drives a real Chromium with Playwright (a library that
controls a browser from Python; `pytest-playwright` gives each test a `page`), and has only two
tests, because a browser costs about a hundred unit tests:

- **Every page runs its script.** Each page ships a "Loading ..." placeholder its script
  replaces once the fetch lands; the test opens every page (and `/solutions?number=1`, the log
  page's "Go to review" path) and requires the placeholder gone and no console error or uncaught
  exception. `expect(...)` retries until the condition holds or times out, so there is no sleep
  anywhere.
- **The log page and the plan's links.** The log page fetches nothing on load, so its sign of
  life is the focused number field. Then the test clicks the Daily Plan's first problem and
  requires `/log?number=N`, the number filled in, and the code field focused.

**A real server, not a TestClient**, so the `coach-web` entry point, the static mount and the
port binding are tested too. The session fixture `base_url` builds an empty database with
`coach init` under `COACH_DB` in a temporary directory, starts `coach-web` as a subprocess on a
port the kernel picks (never 8000, where a dev server may be running), and waits until a real
request answers 200: a process that bound the port and hung still completes the TCP handshake, so
an open port proves nothing. Teardown is `terminate()`, then `kill()` after five seconds. Passing
`--base-url` uses a server already running instead.

Without Chromium (a separate download: `uv run playwright install chromium`) the tests skip, so
`uv run pytest` stays green on a fresh clone. `tests/browser/__init__.py` is empty and
load-bearing: without it, that directory's `conftest.py` shadows `tests/conftest.py`. Deleting a
solve has no browser test, because seeding a solve goes through `/api/log`, and the server it
starts reads `.env`'s real keys; it was clicked through by hand on a copy of the database.

When the tests skip, Playwright prints a `TargetClosedError` on shutdown: it does so whenever
its driver starts and stops without launching a browser, even outside pytest (seen with 1.62.0).
It does not affect the result, and a run with Chromium installed prints none.
