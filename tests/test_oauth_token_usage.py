import pytest

from scripts import test_oauth_token_usage


class _InvalidJsonResponse:
    def raise_for_status(self):
        return None

    def json(self):
        raise ValueError("invalid json")


class _AsyncClientWithInvalidJson:
    def __init__(self, timeout: float):
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get(self, *args, **kwargs):
        return _InvalidJsonResponse()


@pytest.mark.asyncio
async def test_google_calendar_token_returns_false_on_unexpected_response_error(monkeypatch, capsys):
    monkeypatch.setattr(test_oauth_token_usage.httpx, "AsyncClient", _AsyncClientWithInvalidJson)

    assert await test_oauth_token_usage.test_google_calendar_token("access-token") is False

    output = capsys.readouterr().out
    assert "Unexpected error: invalid json" in output
