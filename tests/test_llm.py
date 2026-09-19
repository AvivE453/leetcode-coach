"""llm.py's one promise: a failed call raises LLMUnavailable, never anything else.

Every caller degrades on LLMUnavailable and only on that - service.enrich_solution_now
and review_solution_now both catch it by name. Anything else escaping means POST /api/log
answers 500 for a solve log_solve has already committed. So the translation is the
contract, and these tests are it - once per API, since each SDK raises its own errors.

The autouse conftest fixture strips both API keys, so each test sets a fake one to get
past the have_api_key() guard and reach the call itself.
"""

from types import SimpleNamespace

import anthropic
import httpx2
import openai
import pydantic
import pytest

from coach import llm

ANTHROPIC_MODEL = "claude-sonnet-5"
OPENROUTER_MODEL = "deepseek/deepseek-v4-flash-0731:free"
MODELS = pytest.mark.parametrize("model", [ANTHROPIC_MODEL, OPENROUTER_MODEL])


class Out(pydantic.BaseModel):
    x: int


class FakeClient:
    """A client of either SDK whose every call raises `exc`."""

    def __init__(self, exc):
        self.messages = self.chat = self.completions = self.with_raw_response = self
        self.exc = exc

    def parse(self, **kwargs):
        raise self.exc


class AnthropicAnswering:
    def __init__(self, out):
        self.messages = self
        self.out = out

    def parse(self, **kwargs):
        return SimpleNamespace(stop_reason="end_turn", parsed_output=self.out)


def with_client(monkeypatch, model, client):
    """Give `model`'s API a fake key and `client`."""
    monkeypatch.setenv(llm.key_name(model), "sk-fake-never-used")
    monkeypatch.setattr(llm, "_openrouter" if llm.on_openrouter(model) else "_anthropic", client)


def openrouter_answering(monkeypatch, status, body):
    """The real OpenAI SDK aimed at OpenRouter, over a fake network that answers `body`.

    A fake client would hand back a ready-made choice and skip the SDK's own parsing,
    which is exactly where a malformed answer crashes, so these go through it.
    """

    def respond(request):
        if isinstance(body, Exception):
            raise body
        if isinstance(body, str):
            return httpx2.Response(status, text=body)
        return httpx2.Response(status, json=body)

    client = openai.OpenAI(
        base_url=llm.OPENROUTER_URL,
        api_key="sk-fake-never-used",
        max_retries=0,
        http_client=httpx2.Client(transport=httpx2.MockTransport(respond)),
    )
    with_client(monkeypatch, OPENROUTER_MODEL, client)


def completion(content, finish_reason="stop", **choice):
    """An OpenRouter chat completion whose one choice says `content`."""
    return {
        "id": "gen-1",
        "object": "chat.completion",
        "created": 0,
        "model": OPENROUTER_MODEL,
        "choices": [
            {
                "index": 0,
                "finish_reason": finish_reason,
                "message": {"role": "assistant", "content": content},
                **choice,
            }
        ],
    }


def validation_error():
    try:
        Out(x="not-an-int")
    except pydantic.ValidationError as e:
        return e
    raise AssertionError("expected a ValidationError")


@pytest.mark.parametrize(
    "model, key", [(ANTHROPIC_MODEL, "ANTHROPIC_API_KEY"), (OPENROUTER_MODEL, "OPENROUTER_API_KEY")]
)
def test_missing_api_key_is_unavailable_and_names_the_key_the_model_needs(model, key):
    with pytest.raises(llm.LLMUnavailable, match=key):
        llm.parse("hi", Out, model=model)


def test_the_model_name_picks_the_api(monkeypatch):
    """With both keys set, `vendor/model` goes to OpenRouter and any other name to Anthropic."""
    with_client(monkeypatch, ANTHROPIC_MODEL, AnthropicAnswering(Out(x=1)))
    openrouter_answering(monkeypatch, 200, completion('{"x": 2}'))

    assert llm.parse("hi", Out, model=ANTHROPIC_MODEL) == Out(x=1)
    assert llm.parse("hi", Out, model=OPENROUTER_MODEL) == Out(x=2)


@pytest.mark.parametrize(
    "body, reason",
    [
        (
            {"id": "gen-1", "error": {"code": 503, "message": "Upstream error: Service temporarily overloaded"}},
            "API error 503: .*overloaded",
        ),
        ({"id": "gen-1", "choices": []}, "no choices"),
        ("<html>502 Bad Gateway</html>", "not JSON"),
    ],
    ids=["error-in-place-of-choices", "empty-choices", "not-json"],
)
def test_a_malformed_http_200_from_openrouter_degrades(body, reason, monkeypatch):
    """The regression: each of these reached the SDK's parser, which raised TypeError,
    IndexError or JSONDecodeError - a 500 for a solve log_solve had already saved.
    The first is what an overloaded provider really sent (2026-09-19)."""
    openrouter_answering(monkeypatch, 200, body)

    with pytest.raises(llm.LLMUnavailable, match=reason):
        llm.parse("hi", Out, model=OPENROUTER_MODEL)


def test_an_error_inside_a_choice_is_not_an_answer(monkeypatch):
    """OpenRouter can report a provider failing mid-answer inside the choice, with
    finish_reason "error" - and content that still fits the schema. Parsed as usual,
    the failure would be stored as the model's judgement."""
    body = completion('{"x": 2}', finish_reason="error", error={"code": 502, "message": "Provider disconnected"})
    openrouter_answering(monkeypatch, 200, body)

    with pytest.raises(llm.LLMUnavailable, match="API error 502: Provider disconnected"):
        llm.parse("hi", Out, model=OPENROUTER_MODEL)


@MODELS
def test_a_malformed_model_answer_degrades(model, monkeypatch):
    """The regression: structured output the schema rejects.

    This used to escape as ValidationError straight out of the log path, which
    had already stored the solve - so the tool reported a traceback for work it
    had saved.
    """
    with_client(monkeypatch, model, FakeClient(validation_error()))

    with pytest.raises(llm.LLMUnavailable, match="did not fit the expected schema"):
        llm.parse("hi", Out, model=model)


def test_the_free_daily_limit_says_so_in_one_sentence(monkeypatch):
    """The raw 429 is a JSON dump carrying the account's user id, shown on the log page."""
    body = {
        "error": {
            "message": "Rate limit exceeded: free-models-per-day.",
            "code": 429,
            "metadata": {"limit_source": "openrouter_free_tier_daily"},
        },
        "user_id": "user_x",
    }
    openrouter_answering(monkeypatch, 429, body)

    with pytest.raises(llm.LLMUnavailable) as caught:
        llm.parse("hi", Out, model=OPENROUTER_MODEL)

    assert str(caught.value) == "OpenRouter's free daily limit is used up"


def test_any_other_rate_limit_keeps_the_apis_words(monkeypatch):
    openrouter_answering(monkeypatch, 429, {"error": {"message": "slow down", "code": 429}})

    with pytest.raises(llm.LLMUnavailable, match="rate limited by the API: .*slow down"):
        llm.parse("hi", Out, model=OPENROUTER_MODEL)


@pytest.mark.parametrize(
    "model, error",
    [
        (ANTHROPIC_MODEL, anthropic.APIConnectionError(request=None)),
        (OPENROUTER_MODEL, openai.APIConnectionError(request=None)),
    ],
)
def test_connection_failures_degrade(model, error, monkeypatch):
    with_client(monkeypatch, model, FakeClient(error))

    with pytest.raises(llm.LLMUnavailable, match="could not reach the API"):
        llm.parse("hi", Out, model=model)


@pytest.mark.parametrize(
    "model, error",
    [
        (ANTHROPIC_MODEL, anthropic.AnthropicError("something new and unhandled")),
        (OPENROUTER_MODEL, openai.OpenAIError("something new and unhandled")),
    ],
)
def test_an_unforeseen_sdk_error_degrades(model, error, monkeypatch):
    """Each SDK's base error class is caught, so a failure mode nobody enumerated
    here still degrades rather than reaching the user as a crash."""
    with_client(monkeypatch, model, FakeClient(error))

    with pytest.raises(llm.LLMUnavailable, match="the API call failed"):
        llm.parse("hi", Out, model=model)


def test_a_call_that_times_out_degrades(monkeypatch):
    openrouter_answering(monkeypatch, 200, httpx2.ReadTimeout("timed out"))

    with pytest.raises(llm.LLMUnavailable, match="could not reach the API"):
        llm.parse("hi", Out, model=OPENROUTER_MODEL)


def test_every_call_has_a_time_budget(monkeypatch):
    """The SDKs' defaults are 600 s a try and two retries: a stuck call would hold the
    request (and the log page) for half an hour before degrading."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake-never-used")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-fake-never-used")
    monkeypatch.setattr(llm, "_anthropic", None)
    monkeypatch.setattr(llm, "_openrouter", None)

    for client in (llm.anthropic_client(), llm.openrouter_client()):
        assert (client.max_retries + 1) * client.timeout <= 6 * 60


@MODELS
def test_programming_errors_are_not_swallowed(model, monkeypatch):
    """Deliberately not caught: a TypeError is a bug here, not the API degrading.

    Reporting it as "the model is unavailable" would send someone hunting the
    wrong problem, and `coach enrich` would quietly skip every solution.
    """
    with_client(monkeypatch, model, FakeClient(TypeError("parse() got an unexpected keyword argument")))

    with pytest.raises(TypeError):
        llm.parse("hi", Out, model=model)
