import json
from unittest.mock import patch

import pytest
from starlette.requests import Request

from ada_backend.main import service_error_handler, unhandled_error_handler
from ada_backend.services.errors import ServiceError


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


@pytest.mark.asyncio
async def test_service_error_handler_returns_client_error_without_sentry():
    request = _build_request()
    error = DemoClientError("invalid client request")
    with patch("ada_backend.main.sentry_sdk.capture_exception") as capture_mock:
        response = await service_error_handler(request, error)
    assert response.status_code == 400
    assert json.loads(response.body) == {"detail": "invalid client request"}
    capture_mock.assert_not_called()


@pytest.mark.asyncio
async def test_service_error_handler_returns_server_error_without_explicit_sentry_capture():
    request = _build_request()
    error = DemoServerError("dependency unavailable")
    with patch("ada_backend.main.sentry_sdk.capture_exception") as capture_mock:
        response = await service_error_handler(request, error)
    assert response.status_code == 503
    assert json.loads(response.body) == {"detail": "dependency unavailable"}
    capture_mock.assert_not_called()


@pytest.mark.asyncio
async def test_unhandled_error_handler_returns_generic_500_without_explicit_sentry_capture():
    request = _build_request()
    error = RuntimeError("boom")
    with patch("ada_backend.main.sentry_sdk.capture_exception") as capture_mock:
        response = await unhandled_error_handler(request, error)
    assert response.status_code == 500
    assert json.loads(response.body) == {"detail": "An unexpected server error occurred."}
    capture_mock.assert_not_called()
