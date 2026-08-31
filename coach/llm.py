import os

import anthropic

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


def text(
    prompt: str,
    system: str | None = None,
    max_tokens: int = 4000,
    model: str | None = None,
) -> str:
    """One plain-text call."""
    kwargs = {"system": system} if system is not None else {}
    response = _complete(
        lambda: client().messages.create(
            model=model or config.MODEL,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
            **kwargs,
        )
    )
    return "".join(block.text for block in response.content if block.type == "text").strip()
