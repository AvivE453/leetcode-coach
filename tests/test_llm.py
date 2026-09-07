"""llm.py's one promise: a failed call raises LLMUnavailable, never anything else.

Every caller degrades on LLMUnavailable and only on that - service.enrich_solution_now
and review_solution_now both catch it by name. Anything else escaping means `coach log`
ends in a traceback and POST /api/log answers 500, for a solve log_solve has already
committed. So the translation is the contract, and these tests are it.

The autouse conftest fixture strips the API key, so each test sets a fake one to get
past the have_api_key() guard and reach the call itself.
"""

import anthropic
import pydantic
import pytest

from coach import llm


class Out(pydantic.BaseModel):
    x: int


class FakeClient:
    """A client whose every call raises `exc`."""

    def __init__(self, exc):
        self.messages = self
        self.exc = exc

    def parse(self, **kwargs):
        raise self.exc

    def create(self, **kwargs):
        raise self.exc


@pytest.fixture
def api_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake-never-used")


def raising(monkeypatch, exc):
    monkeypatch.setattr(llm, "_client", FakeClient(exc))


def validation_error():
    try:
        Out(x="not-an-int")
    except pydantic.ValidationError as e:
        return e
    raise AssertionError("expected a ValidationError")


def test_missing_api_key_is_unavailable_not_a_crash():
    with pytest.raises(llm.LLMUnavailable, match="ANTHROPIC_API_KEY"):
        llm.parse("hi", Out)


def test_a_malformed_model_answer_degrades(api_key, monkeypatch):
    """The regression: structured output the schema rejects.

    This used to escape as ValidationError straight through `coach log`, which
    had already stored the solve - so the tool reported a traceback for work it
    had saved.
    """
    raising(monkeypatch, validation_error())

    with pytest.raises(llm.LLMUnavailable, match="did not fit the expected schema"):
        llm.parse("hi", Out)


def test_connection_failures_degrade(api_key, monkeypatch):
    raising(monkeypatch, anthropic.APIConnectionError(request=None))

    with pytest.raises(llm.LLMUnavailable, match="could not reach the API"):
        llm.parse("hi", Out)


def test_an_unforeseen_sdk_error_degrades(api_key, monkeypatch):
    """AnthropicError is the base of every SDK error, so a failure mode nobody
    enumerated here still degrades rather than reaching the user as a crash."""
    raising(monkeypatch, anthropic.AnthropicError("something new and unhandled"))

    with pytest.raises(llm.LLMUnavailable, match="the API call failed"):
        llm.parse("hi", Out)


def test_programming_errors_are_not_swallowed(api_key, monkeypatch):
    """Deliberately not caught: a TypeError is a bug here, not the API degrading.

    Reporting it as "the model is unavailable" would send someone hunting the
    wrong problem, and `coach enrich` would quietly skip every solution.
    """
    raising(monkeypatch, TypeError("parse() got an unexpected keyword argument"))

    with pytest.raises(TypeError):
        llm.parse("hi", Out)
