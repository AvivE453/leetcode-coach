import pytest


@pytest.fixture(autouse=True)
def no_api_key(monkeypatch):
    """Tests must never hit the real API: config.py loads .env at import,
    so strip the key from the environment for every test."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
