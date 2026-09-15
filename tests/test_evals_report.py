"""What the feedback eval writes down when it disagrees with the model.

These two lines are the working surface of the whole harness. RESULTS.md's summary
says the 93%->97% movement came not from prompt work but from three defects found
in the bank itself - each one found by reading a miss, disagreeing with our own
label, and checking. A miss that names only the two categories ("planted
edge-case, reported bug") cannot be adjudicated by anyone; the evidence that
produced the label is what makes it an argument rather than a score.

So these tests exist to stop the evidence being tidied back out of the report - and
to keep it out of the one place it must not be read: a test split not yet revealed.
"""

from evals import run_evals

FIXTURE = {
    "slug": "valid-parentheses",
    "id": "no-underflow-guard",
    "category": "bug",
    "evidence": "input=(']',) expected=False raised IndexError: pop from empty list",
    "code": "...",
}

QUIET = {"issues": [], "verdict": "optimal"}
FLAGGED = {"issues": [{"category": "edge-case", "description": "Returns None with no pair."}],
           "verdict": "acceptable"}


def control(fixture_id, split="dev", kind="representative", origin="authored"):
    return {"slug": "two-sum", "id": fixture_id, "category": None, "split": split,
            "control": kind, "origin": origin, "code": "..."}


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

    line = run_evals.false_positive_line(control("canonical"), issues)

    assert "two-sum/canonical" in line
    assert "The inner loop rescans the array." in line
    assert "Empty input is unhandled." in line
    assert "complexity" in line and "edge-case" in line


def test_a_false_positive_on_private_code_names_its_categories_but_not_the_claim():
    """RESULTS.md is public and a claim can quote the code it is about."""
    issues = [{"category": "edge-case", "description": "`nums[i] + nums[j]` is never checked."}]

    line = run_evals.false_positive_line(control("aviv-3", origin="aviv"), issues)

    assert "two-sum/aviv-3" in line and "edge-case" in line
    assert "nums[i]" not in line


def test_regression_controls_are_scored_apart_from_the_headline_rate():
    """A regression control probes a false positive already seen, so it must not flatter the headline."""
    fixtures = [control("canonical"), control("store-complement"),
                control("relies-on-guaranteed-answer", kind="regression")]

    dev = run_evals.score_feedback(fixtures, [QUIET, QUIET, FLAGGED])["dev"]

    assert (dev["false_positive_rate"], dev["clean_controls"]) == (0.0, 2)
    assert dev["false_positives"] == []
    assert (dev["regression_false_positive_rate"], dev["regression_controls"]) == (1.0, 1)
    assert "two-sum/relies-on-guaranteed-answer" in dev["regression_false_positives"][0]


def test_each_split_is_scored_from_its_own_fixtures():
    fixtures = [control("canonical", split="dev"), control("neetcode", split="test", origin="neetcode")]

    scores = run_evals.score_feedback(fixtures, [FLAGGED, QUIET])

    assert (scores["dev"]["false_positive_rate"], scores["dev"]["clean_controls"]) == (1.0, 1)
    assert (scores["test"]["false_positive_rate"], scores["test"]["clean_controls"]) == (0.0, 1)


def test_false_positives_are_broken_down_by_who_wrote_the_code():
    fixtures = [control("neetcode", origin="neetcode"), control("walkccc", origin="walkccc"),
                control("aviv-3", origin="aviv")]

    by_origin = run_evals.score_feedback(fixtures, [QUIET, QUIET, FLAGGED])["dev"]["false_positives_by_origin"]

    assert by_origin == {"aviv": {"controls": 1, "false_positives": 1},
                         "neetcode": {"controls": 1, "false_positives": 0},
                         "walkccc": {"controls": 1, "false_positives": 0}}


def test_a_hidden_test_split_reports_its_numbers_but_not_what_it_got_wrong():
    fixtures = [control("canonical", split="dev"), control("neetcode", split="test", origin="neetcode")]
    scores = run_evals.score_feedback(fixtures, [FLAGGED, FLAGGED])
    scores["test"] = run_evals.hide_details(scores["test"])

    report = "\n".join(run_evals.feedback_lines({"prompt_version": "review-v9", "splits": scores}))
    dev_part, test_part = report.split("split `test`")

    assert "two-sum/canonical" in dev_part
    assert "details hidden" in test_part
    assert "two-sum/neetcode" not in test_part
    assert "Returns None with no pair." not in test_part
