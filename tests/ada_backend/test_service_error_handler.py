import json

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from ada_backend.error_handlers import register_error_handlers
from ada_backend.services.errors import ServiceError
from engine.components.errors import LLMProviderError, MissingKeyPromptTemplateError
from engine.errors import EngineError
from engine.field_expressions.errors import FieldExpressionError


class DemoClientError(ServiceError):
    status_code = 400

    def __init__(self, message: str = "client failure"):
        super().__init__(message)


class DemoServerError(ServiceError):
    status_code = 503

    def __init__(self, message: str = "server failure"):
        super().__init__(message)


def _build_request() -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/test",
        "raw_path": b"/test",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "root_path": "",
    }
    return Request(scope)


def _get_handlers() -> dict:
    """Register handlers on a throwaway app and return them keyed by exception type."""
    app = FastAPI()
    register_error_handlers(app)
    return app.exception_handlers


@pytest.mark.asyncio
async def test_service_error_handler_returns_client_error():
    handler = _get_handlers()[ServiceError]
    response = await handler(_build_request(), DemoClientError("invalid client request"))
    assert response.status_code == 400
    assert json.loads(response.body) == {"detail": "invalid client request"}


@pytest.mark.asyncio
async def test_service_error_handler_returns_server_error():
    handler = _get_handlers()[ServiceError]
    response = await handler(_build_request(), DemoServerError("dependency unavailable"))
    assert response.status_code == 503
    assert json.loads(response.body) == {"detail": "An internal error occurred."}


@pytest.mark.asyncio
async def test_service_error_5xx_with_safe_detail():
    """5xx errors with _safe_detail expose the safe message instead of the generic one."""

    class SafeServerError(ServiceError):
        status_code = 503
        _safe_detail = "Service temporarily unavailable"

        def __init__(self):
            super().__init__("internal: redis connection pool exhausted")

    handler = _get_handlers()[ServiceError]
    exc = SafeServerError()
    assert str(exc) == "internal: redis connection pool exhausted"
    response = await handler(_build_request(), exc)
    assert response.status_code == 503
    assert json.loads(response.body) == {"detail": "Service temporarily unavailable"}


@pytest.mark.asyncio
async def test_unhandled_error_handler_returns_generic_500():
    handler = _get_handlers()[Exception]
    response = await handler(_build_request(), RuntimeError("boom"))
    assert response.status_code == 500
    assert json.loads(response.body) == {"detail": "An unexpected server error occurred."}


def test_http_exception_uses_specific_handler_over_generic_handler():
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/raises-http")
    def raises_http_exception():
        raise HTTPException(status_code=404, detail="Not found")

    client = TestClient(app)
    response = client.get("/raises-http")

    assert response.status_code == 404
    assert response.json() == {"detail": "Not found"}


class TestEngineErrorHandler:
    @pytest.mark.asyncio
    async def test_engine_error_returns_400_with_message(self):
        handler = _get_handlers()[EngineError]
        exc = MissingKeyPromptTemplateError(missing_keys=["name", "role"])
        response = await handler(_build_request(), exc)
        assert response.status_code == 400
        body = json.loads(response.body)
        assert "name" in body["detail"]
        assert "role" in body["detail"]

    @pytest.mark.asyncio
    async def test_field_expression_error_returns_400(self):
        handler = _get_handlers()[EngineError]
        exc = FieldExpressionError("bad expression")
        response = await handler(_build_request(), exc)
        assert response.status_code == 400
        assert json.loads(response.body) == {"detail": "bad expression"}


class TestLLMProviderErrorHandler:
    @pytest.mark.asyncio
    async def test_rate_limit_returns_429(self):
        handler = _get_handlers()[LLMProviderError]
        exc = LLMProviderError("Rate limit exceeded", status_code=429, provider_name="OpenAI")
        response = await handler(_build_request(), exc)
        assert response.status_code == 429
        body = json.loads(response.body)
        assert "OpenAI" in body["detail"]
        assert "Rate limit" in body["detail"]

    @pytest.mark.asyncio
    async def test_server_error_returns_502(self):
        handler = _get_handlers()[LLMProviderError]
        exc = LLMProviderError("Internal server error", status_code=500, provider_name="Anthropic")
        response = await handler(_build_request(), exc)
        assert response.status_code == 502

    @pytest.mark.asyncio
    async def test_no_status_code_returns_502(self):
        handler = _get_handlers()[LLMProviderError]
        exc = LLMProviderError("Connection reset", status_code=None)
        response = await handler(_build_request(), exc)
        assert response.status_code == 502
