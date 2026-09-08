"""Guards on the seam between a page and the script that drives it.

A page script reaches into its markup by id, and the markup never mentions the
script - so nothing in either file fails when one is renamed and the other is
not. `getElementById` returns null, and the page breaks wherever that null is
first used. That is not hypothetical: weekly.js once reached for `note` and
`run-meta` after weekly.html had dropped them, and the null landed *inside the
catch block that was supposed to report the failure* - so the page sat on its
loading text with nothing on screen to say why, while the server logged a 200.

Nothing here shares code with what it checks, exactly like test_vocabulary.py:
these tests are the only thing that can notice the drift.

The parsing is deliberately plain regex over our own hand-written markup rather
than an HTML parser - and every check below is paired with an assertion that it
actually matched something, because a pattern that silently matches nothing
would pass forever.
"""

import re

from coach.web.app import STATIC_DIR

# Every id lookup in the page scripts today is a string literal, which is what
# makes a text guard complete rather than approximate - and what
# test_every_id_lookup_is_a_literal_the_guard_can_see keeps true.
ID_LOOKUP = re.compile(r'getElementById\("([^"]+)"\)')
ANY_ID_LOOKUP = re.compile(r"getElementById\(")
# The lookbehind is load-bearing: `\bid="` also matches `data-id="` and any other
# `*-id="` attribute, which would count as declaring an id that getElementById
# cannot find - a false pass in the one check this file exists for.
DECLARED_ID = re.compile(r'(?<![\w-])id="([^"]+)"')
PAGE_SCRIPT = re.compile(r'<script src="/static/([^"]+)">')
ARIA_REF = re.compile(r'\baria-(?:controls|labelledby|describedby)="([^"]+)"')
NAME_SELECTOR = re.compile(r'\[name="([^"]+)"\]')

SHARED_SCRIPT = "dom.js"


def pages() -> list[tuple[str, str, list[str]]]:
    """(page name, markup, scripts it loads in order) for every page in static/.

    Discovered rather than listed, so a fifth page is covered the day it is
    added instead of the day someone remembers to add it here.
    """
    found = []
    for html in sorted(STATIC_DIR.glob("*.html")):
        markup = html.read_text()
        found.append((html.name, markup, PAGE_SCRIPT.findall(markup)))
    return found


def script_text(name: str) -> str:
    return (STATIC_DIR / name).read_text()


def test_the_page_scan_finds_the_pages_and_their_scripts():
    """Everything below is a subset check, and a subset check over nothing passes.

    So this is the test that has to fail if the glob or either pattern stops
    matching - the rest are only meaningful while this holds.
    """
    found = pages()
    assert len(found) == 4, [name for name, _, _ in found]

    for name, markup, scripts in found:
        assert DECLARED_ID.findall(markup), f"{name}: no ids found - has the markup changed?"
        assert len(scripts) >= 2, f"{name}: expected the shared script plus its own, got {scripts}"

    looked_up = {i for _, _, scripts in found for s in scripts for i in ID_LOOKUP.findall(script_text(s))}
    assert len(looked_up) > 20, f"only {len(looked_up)} id lookups found across every script"


def test_every_page_script_finds_the_elements_it_reaches_for():
    """The one that would have caught the incident in the module docstring."""
    for name, markup, scripts in pages():
        declared = set(DECLARED_ID.findall(markup))
        for script in scripts:
            missing = sorted(set(ID_LOOKUP.findall(script_text(script))) - declared)
            assert not missing, (
                f"{script} looks up {missing}, which {name} does not declare -"
                f" getElementById would return null at runtime"
            )


def test_every_id_lookup_is_a_literal_the_guard_can_see():
    """A computed lookup would slip past ID_LOOKUP and be silently unguarded.

    Making that a failing test rather than a quiet gap turns it into a decision:
    either keep the literal, or widen this file on purpose.
    """
    for _, _, scripts in pages():
        for script in scripts:
            source = script_text(script)
            assert len(ANY_ID_LOOKUP.findall(source)) == len(ID_LOOKUP.findall(source)), (
                f"{script} calls getElementById with something other than a string"
                f" literal, so the id it needs is no longer checked against the markup"
            )


def test_every_page_loads_the_shared_helpers_before_its_own_script():
    """dom.js defines el/getJSON/topicCard as globals - order is load-bearing.

    Loaded late (or not at all), the page script throws a ReferenceError on its
    first call and renders nothing.
    """
    for name, _, scripts in pages():
        assert SHARED_SCRIPT in scripts, f"{name} never loads {SHARED_SCRIPT}"
        own = [s for s in scripts if s != SHARED_SCRIPT]
        assert own, f"{name} loads no page script of its own"
        assert scripts.index(SHARED_SCRIPT) < min(scripts.index(s) for s in own), (
            f"{name} loads {SHARED_SCRIPT} after {own} - el() would be undefined"
        )


def test_every_aria_reference_points_at_an_element_on_the_page():
    """A renamed heading id breaks the association silently, like a renamed hook."""
    checked = 0
    for name, markup, _ in pages():
        declared = set(DECLARED_ID.findall(markup))
        for attribute in ARIA_REF.findall(markup):
            for target in attribute.split():
                checked += 1
                assert target in declared, f"{name}: aria reference to missing id {target!r}"
    assert checked > 5, f"only {checked} aria references found - has the pattern stopped matching?"


def test_every_name_selector_matches_the_form_it_queries():
    """home.js reads the outcome radios by name; renamed, the form stops submitting."""
    checked = 0
    for name, markup, scripts in pages():
        for script in scripts:
            for group in NAME_SELECTOR.findall(script_text(script)):
                checked += 1
                assert f'name="{group}"' in markup, (
                    f"{script} queries [name={group!r}], which {name} has no field for"
                )
    assert checked, "no [name=...] selectors found - has the pattern stopped matching?"
