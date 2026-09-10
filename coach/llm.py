import os

import anthropic
from pydantic import ValidationError

from coach import config


class LLMUnavailable(Exception):
    """The API can't be used right now (no key, network/API failure, or refusal)."""


def have_api_key() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


_client: anthropic.Anthropic | None = None


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        # Identity-linked API keys must name the workspace they act in.
        workspace = os.environ.get("ANTHROPIC_WORKSPACE_ID")
        _client = anthropic.Anthropic(
            default_headers={"anthropic-workspace-id": workspace} if workspace else None
        )
    return _client


def _complete(request):
    """Run one API call, translating every failure mode into LLMUnavailable.

    The SDK already retries rate limits and 5xx with backoff; anything that
    still fails is wrapped so callers can degrade gracefully.

    The three specific handlers exist for their wording; the last two are the
    ones that make the contract true. A model that answers with output the
    schema rejects used to raise ValidationError straight out of the log path,
    which had already committed the solve - so the tool reported a traceback
    for work it had saved. Programming errors (TypeError, AttributeError) are
    deliberately NOT caught: those are bugs here, not the API degrading.
    """
    if not have_api_key():
        raise LLMUnavailable("ANTHROPIC_API_KEY is not set - add it to .env at the project root")
    try:
        response = request()
    except anthropic.RateLimitError as e:
        raise LLMUnavailable(f"rate limited by the API: {e.message}") from e
    except anthropic.APIStatusError as e:
        raise LLMUnavailable(f"API error {e.status_code}: {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise LLMUnavailable(f"could not reach the API: {e}") from e
    except ValidationError as e:
        raise LLMUnavailable(
            f"the model's answer did not fit the expected schema ({e.error_count()} field error(s))"
        ) from e
    except anthropic.AnthropicError as e:
        # Base class of every SDK error - the catch-all so a new or rarer
        # failure mode degrades instead of surfacing as a crash.
        raise LLMUnavailable(f"the API call failed: {e}") from e

    if response.stop_reason == "refusal":
        raise LLMUnavailable("the model declined this request")
    if response.stop_reason == "max_tokens":
        raise LLMUnavailable("response truncated at max_tokens")
    return response


def parse(
    prompt: str,
    output_format,
    system: str | None = None,
    max_tokens: int = 16000,
    model: str | None = None,
):
    """One structured-output call: prompt in, validated Pydantic instance out."""
    kwargs = {"system": system} if system is not None else {}
    response = _complete(
        lambda: client().messages.parse(
            model=model or config.MODEL,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
            output_format=output_format,
            **kwargs,
        )
    )
    return response.parsed_output
