from uuid import uuid4

import pytest

import webhook_scripts.webhook_main as webhook_main


class DummyResponse:
    def __init__(self, status_code: int, json_data=None):
        self.status_code = status_code
        self.request = object()
        self._json_data = json_data or {}

    def json(self):
        return self._json_data

    def raise_for_status(self):
        pass


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


class CapturingClient:
    """Records the kwargs passed to post() and returns a canned response."""

    def __init__(self):
        self.captured_kwargs: dict | None = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, **kwargs):
        self.captured_kwargs = {"url": url, **kwargs}
        return DummyResponse(status_code=202, json_data={"status": "accepted", "run_id": str(uuid4())})


@pytest.mark.asyncio
async def test_direct_trigger_wraps_payload_in_input_data(monkeypatch):
    """Regression: _run_direct_trigger must send {"input_data": <payload>} not the raw payload."""
    client = CapturingClient()
    monkeypatch.setattr(webhook_main.httpx, "AsyncClient", lambda: client)
    monkeypatch.setenv("ADA_URL", "http://test")
    monkeypatch.setenv("WEBHOOK_API_KEY", "key")

    user_payload = {"messages": [{"role": "user", "content": "hello"}]}
    await webhook_main.webhook_main_async(
        webhook_id=uuid4(),
        provider="direct_trigger",
        event_id="evt-1",
        payload={**user_payload, "env": "production"},
    )

    body = client.captured_kwargs["json"]
    assert "input_data" in body, "Body must wrap payload under 'input_data'"
    assert body["input_data"] == user_payload
