"""The one failure no cheaper test can see: the JavaScript did not run.

test_web.py asserts on JSON and never runs a script; test_static_pages.py reads
the scripts and never executes them. So a script that throws on line one leaves
every page blank and all 192 of them green. That is what this file is for, and
it is deliberately the only browser test - a browser costs ~100x a unit test, so
it earns its place only where nothing cheaper can reach.
"""

from playwright.sync_api import Page, expect

# Each page ships a placeholder that its script is supposed to replace once the
# fetch lands. Still showing means one of two things went wrong: the request
# failed, or it succeeded and the script read fields the JSON does not have -
# and the second is silent, because a missing key in JavaScript is `undefined`,
# not an error.
PAGES = {
    "/": "Loading your numbers",
    "/solutions": "Loading your solutions",
    "/plan": "Loading the plan",
    "/weekly": "Loading this week",
}


def test_every_page_runs_its_script_and_renders(page: Page, base_url):
    problems: list[str] = []
    page.on("console", lambda msg: problems.append(msg.text) if msg.type == "error" else None)
    page.on("pageerror", lambda err: problems.append(str(err)))

    for path, placeholder in PAGES.items():
        page.goto(base_url + path)
        # not_to_be_visible, not a count: /solutions leaves the paragraph in the
        # DOM and sets `hidden` on it, and a person cannot read a hidden
        # paragraph. The assertion also retries, which is what waits out the
        # fetch - there is no explicit wait anywhere in this test.
        expect(page.get_by_text(placeholder)).not_to_be_visible()

    assert problems == []
