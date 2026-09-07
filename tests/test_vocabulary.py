"""Guards on vocabularies that must agree but cannot import one another.

Typer needs an Enum, pydantic needs a Literal, SQLite needs a CHECK clause, and
the scheduler needs a dict it can score - so the same four outcome names are
declared four times, by necessity rather than by neglect. Same story for the
planner's pattern->tag map against the enrichment vocabulary.

These tests are the seam: nothing here shares code, so something has to fail
loudly when one copy drifts from the others.
"""

import re
from typing import get_args

from coach import cli, db, enrich, scheduler
from coach.web.app import LogRequest
from coach.weekly import plan

OUTCOMES = set(scheduler.QUALITY)


def test_cli_and_api_accept_exactly_the_outcomes_the_scheduler_scores():
    """An outcome either side accepted but QUALITY lacked would KeyError on log."""
    assert {o.value for o in cli.Outcome} == OUTCOMES
    assert set(get_args(LogRequest.model_fields["outcome"].annotation)) == OUTCOMES


def test_the_attempts_table_accepts_exactly_those_outcomes():
    """A name the app accepts but the CHECK rejects fails at INSERT, after the LLM spend."""
    clause = re.search(r"outcome IN \(([^)]*)\)", db.SCHEMA).group(1)
    assert {value.strip().strip("'") for value in clause.split(",")} == OUTCOMES


def test_every_planner_tag_key_is_a_real_pattern():
    """A typo'd key silently stops targeting that pattern, exactly like a missing one.

    Subset, not equality: patterns with no usable official tag are left out on
    purpose (see PATTERN_TO_TAG) and fall through to curriculum progression.
    """
    unknown = set(plan.PATTERN_TO_TAG) - set(enrich.PATTERNS)
    assert not unknown, f"PATTERN_TO_TAG keys are not patterns: {sorted(unknown)}"
