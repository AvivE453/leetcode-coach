"""What the feedback eval writes down when it disagrees with the model.

These two lines are the working surface of the whole harness. RESULTS.md's summary
says the 93%->97% movement came not from prompt work but from three defects found
in the bank itself - each one found by reading a miss, disagreeing with our own
label, and checking. A miss that names only the two categories ("planted
edge-case, reported bug") cannot be adjudicated by anyone; the evidence that
produced the label is what makes it an argument rather than a score.

So these tests exist to stop the evidence being tidied back out of the report.
"""

from evals import run_evals

FIXTURE = {
    "slug": "valid-parentheses",
    "id": "no-underflow-guard",
    "category": "bug",
    "evidence": "input=(']',) expected=False raised IndexError: pop from empty list",
    "code": "...",
}


def test_a_miss_carries_the_execution_proof_of_the_label():
    line = run_evals.miss_line(FIXTURE, {"edge-case"})

    assert "valid-parentheses/no-underflow-guard" in line
    assert "planted bug" in line
    assert FIXTURE["evidence"] in line, "without this a reader cannot judge the disagreement"
    assert "reported ['edge-case']" in line


def test_a_miss_says_so_when_nothing_at_all_was_reported():
    """The starkest disagreement, and the one most likely to be a bank defect."""
    line = run_evals.miss_line(FIXTURE, set())

    assert "reported nothing" in line
    assert FIXTURE["evidence"] in line


def test_a_false_positive_quotes_the_claim_not_just_its_category():
    issues = [
        {"category": "complexity", "description": "The inner loop rescans the array."},
        {"category": "edge-case", "description": "Empty input is unhandled."},
    ]

    line = run_evals.false_positive_line(FIXTURE, issues)

    assert "valid-parentheses" in line
    assert "The inner loop rescans the array." in line
    assert "Empty input is unhandled." in line
    assert "complexity" in line and "edge-case" in line


def test_regression_controls_are_scored_apart_from_the_headline_rate():
    """A regression control probes a false positive already seen, so it must not flatter the headline."""
    def control(kind, fixture_id):
        return {"slug": "two-sum", "id": fixture_id, "category": None, "control": kind, "code": "..."}

    fixtures = [
        control("representative", "canonical"),
        control("representative", "store-complement"),
        control("regression", "relies-on-guaranteed-answer"),
    ]
    quiet = {"issues": [], "verdict": "optimal"}
    flagged = {"issues": [{"category": "edge-case", "description": "Returns None with no pair."}],
               "verdict": "acceptable"}

    scored = run_evals.score_feedback(fixtures, [quiet, quiet, flagged])

    assert (scored["false_positive_rate"], scored["clean_controls"]) == (0.0, 2)
    assert scored["false_positives"] == []
    assert (scored["regression_false_positive_rate"], scored["regression_controls"]) == (1.0, 1)
    assert "two-sum/relies-on-guaranteed-answer" in scored["regression_false_positives"][0]
