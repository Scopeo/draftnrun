import pytest

import webhook_scripts.webhook_main as webhook_main


class DummyResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code
        self.request = object()


class DummyClient:
    def __init__(self, exception):
        self._exception = exception

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, *args, **kwargs):
        raise self._exception


@pytest.mark.asyncio
async def test_post_maps_5xx_to_retryable(monkeypatch):
    exc = webhook_main.httpx.HTTPStatusError(
        "server error",
        request=object(),
        response=DummyResponse(status_code=503),
    )
    monkeypatch.setattr(webhook_main.httpx, "AsyncClient", lambda: DummyClient(exc))

    with pytest.raises(webhook_main.RetryableWebhookError):
        await webhook_main._post("http://x", {}, "k", "ctx")


@pytest.mark.asyncio
async def test_post_maps_4xx_to_fatal(monkeypatch):
    exc = webhook_main.httpx.HTTPStatusError(
        "client error",
        request=object(),
        response=DummyResponse(status_code=400),
    )
    monkeypatch.setattr(webhook_main.httpx, "AsyncClient", lambda: DummyClient(exc))

    with pytest.raises(webhook_main.FatalWebhookError):
        await webhook_main._post("http://x", {}, "k", "ctx")


@pytest.mark.asyncio
async def test_post_maps_network_errors_to_retryable(monkeypatch):
    exc = webhook_main.httpx.RequestError("network down", request=object())
    monkeypatch.setattr(webhook_main.httpx, "AsyncClient", lambda: DummyClient(exc))

    with pytest.raises(webhook_main.RetryableWebhookError):
        await webhook_main._post("http://x", {}, "k", "ctx")
