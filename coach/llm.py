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


def parse(prompt: str, output_format, system: str | None = None, max_tokens: int = 16000):
    """One structured-output call: prompt in, validated Pydantic instance out.

    The SDK already retries rate limits and 5xx with backoff; anything that
    still fails is wrapped in LLMUnavailable so callers can degrade gracefully.
    """
    if not have_api_key():
        raise LLMUnavailable("ANTHROPIC_API_KEY is not set - add it to .env at the project root")

    kwargs = {}
    if system is not None:
        kwargs["system"] = system
    try:
        response = client().messages.parse(
            model=config.MODEL,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
            output_format=output_format,
            **kwargs,
        )
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
    return response.parsed_output
