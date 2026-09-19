import os

import anthropic
import openai
from pydantic import ValidationError

from coach import config

OPENROUTER_URL = "https://openrouter.ai/api/v1"

# Past this a call is stuck, not slow: the slowest answer seen, a free model tagging a
# solve, took about two minutes. With one retry a stuck call holds the request (and the
# page waiting on it) for six minutes at most, where the SDKs' own defaults - 600 s a
# try, two retries - would hold it for half an hour.
CALL_TIMEOUT = 180.0
CALL_RETRIES = 1


class LLMUnavailable(Exception):
    """The API can't be used right now (no key, network/API failure, or refusal)."""


def on_openrouter(model: str) -> bool:
    """OpenRouter names every model `vendor/model`; Anthropic's own ids have no slash."""
    return "/" in model


def key_name(model: str) -> str:
    return "OPENROUTER_API_KEY" if on_openrouter(model) else "ANTHROPIC_API_KEY"


def have_api_key(model: str | None = None) -> bool:
    return bool(os.environ.get(key_name(model or config.MODEL)))


_anthropic: anthropic.Anthropic | None = None
_openrouter: openai.OpenAI | None = None


def anthropic_client() -> anthropic.Anthropic:
    global _anthropic
    if _anthropic is None:
        # Identity-linked API keys must name the workspace they act in.
        workspace = os.environ.get("ANTHROPIC_WORKSPACE_ID")
        _anthropic = anthropic.Anthropic(
            default_headers={"anthropic-workspace-id": workspace} if workspace else None,
            timeout=CALL_TIMEOUT,
            max_retries=CALL_RETRIES,
        )
    return _anthropic


def openrouter_client() -> openai.OpenAI:
    global _openrouter
    if _openrouter is None:
        _openrouter = openai.OpenAI(
            base_url=OPENROUTER_URL,
            api_key=os.environ["OPENROUTER_API_KEY"],
            timeout=CALL_TIMEOUT,
            max_retries=CALL_RETRIES,
        )
    return _openrouter


def _free_daily_limit(e) -> bool:
    """OpenRouter's daily cap on free models, told apart from a passing per-minute limit.

    Its message is the raw error body, user id included, so it gets a sentence of its own.
    """
    body = e.body if isinstance(e.body, dict) else {}
    return (body.get("metadata") or {}).get("limit_source") == "openrouter_free_tier_daily"


def _complete(model: str, request):
    """Run one API call, translating every failure mode into LLMUnavailable.

    Both SDKs already retry rate limits and 5xx with backoff; anything that
    still fails is wrapped so callers can degrade gracefully. The two name
    their errors alike, so each handler takes the pair.

    The specific handlers exist for their wording; the last two are the
    ones that make the contract true. A model that answers with output the
    schema rejects used to raise ValidationError straight out of the log path,
    which had already committed the solve - so the tool reported a traceback
    for work it had saved. Programming errors (TypeError, AttributeError) are
    deliberately NOT caught: those are bugs here, not the API degrading.
    """
    if not have_api_key(model):
        raise LLMUnavailable(f"{key_name(model)} is not set - add it to .env at the project root")
    try:
        return request()
    except (anthropic.RateLimitError, openai.RateLimitError) as e:
        if _free_daily_limit(e):
            raise LLMUnavailable("OpenRouter's free daily limit is used up") from e
        raise LLMUnavailable(f"rate limited by the API: {e.message}") from e
    except (anthropic.APIStatusError, openai.APIStatusError) as e:
        raise LLMUnavailable(f"API error {e.status_code}: {e.message}") from e
    except (anthropic.APIConnectionError, openai.APIConnectionError) as e:
        raise LLMUnavailable(f"could not reach the API: {e}") from e
    except openai.LengthFinishReasonError as e:
        raise LLMUnavailable("response truncated at max_tokens") from e
    except ValidationError as e:
        raise LLMUnavailable(
            f"the model's answer did not fit the expected schema ({e.error_count()} field error(s))"
        ) from e
    except (anthropic.AnthropicError, openai.OpenAIError) as e:
        # Base class of every error each SDK raises - the catch-all so a new or
        # rarer failure mode degrades instead of surfacing as a crash.
        raise LLMUnavailable(f"the API call failed: {e}") from e


def _parse_anthropic(model, prompt, output_format, system, max_tokens):
    kwargs = {"system": system} if system is not None else {}
    response = anthropic_client().messages.parse(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
        output_format=output_format,
        **kwargs,
    )
    if response.stop_reason == "refusal":
        raise LLMUnavailable("the model declined this request")
    if response.stop_reason == "max_tokens":
        raise LLMUnavailable("response truncated at max_tokens")
    return response.parsed_output


def _openrouter_message(raw):
    """The parsed message of a raw OpenRouter response, or LLMUnavailable saying why not.

    OpenRouter reports a failed call as HTTP 200 in two shapes: an `error` in place of
    choices (an overloaded provider, say), and an `error` inside a choice that finished
    with "error" - which can still carry content that fits the schema, so parsing it
    would pass the failure off as the model's answer. The body is checked before the
    SDK parses it, because the SDK meets anything malformed (no JSON, no choices) with
    a TypeError or IndexError, which would escape as a bug and 500 a solve already saved.
    """
    try:
        body = raw.http_response.json()
    except ValueError as e:
        raise LLMUnavailable("the API's answer was not JSON") from e
    if not isinstance(body, dict):
        raise LLMUnavailable("the API's answer was not a JSON object")
    if body.get("error"):
        raise LLMUnavailable(_api_error(body["error"]))
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise LLMUnavailable("the API's answer had no choices")
    choice = choices[0]
    if choice.get("error") or choice.get("finish_reason") == "error":
        raise LLMUnavailable(_api_error(choice.get("error")))
    if not isinstance(choice.get("message"), dict):
        raise LLMUnavailable("the API's answer had no message")
    return raw.parse().choices[0].message


def _api_error(error) -> str:
    if isinstance(error, dict):
        return f"API error {error.get('code')}: {error.get('message')}"
    return f"API error: {error or 'the provider stopped with an error'}"


def _parse_openrouter(model, prompt, output_format, system, max_tokens):
    messages = [{"role": "user", "content": prompt}]
    if system is not None:
        messages.insert(0, {"role": "system", "content": system})
    raw = openrouter_client().chat.completions.with_raw_response.parse(
        model=model,
        max_tokens=max_tokens,
        messages=messages,
        response_format=output_format,
        # Route only to a provider that enforces the schema: one that ignored
        # response_format would answer in free text, and every answer would fail.
        extra_body={"provider": {"require_parameters": True}},
    )
    message = _openrouter_message(raw)
    if message.parsed is None:
        raise LLMUnavailable(
            "the model declined this request" if message.refusal else "the model returned no answer"
        )
    return message.parsed


def parse(
    prompt: str,
    output_format,
    system: str | None = None,
    max_tokens: int = 16000,
    model: str | None = None,
):
    """One structured-output call: prompt in, validated Pydantic instance out.

    The model's name picks the API (`on_openrouter`), and with it the key it needs.
    """
    model = model or config.MODEL
    call = _parse_openrouter if on_openrouter(model) else _parse_anthropic
    return _complete(model, lambda: call(model, prompt, output_format, system, max_tokens))
