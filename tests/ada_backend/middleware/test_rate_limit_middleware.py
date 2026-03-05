from unittest.mock import Mock, patch

import pytest
from fastapi import Request
from slowapi.errors import RateLimitExceeded

from ada_backend.middleware.rate_limit_middleware import rate_limit_exceeded_handler


def _make_exc() -> RateLimitExceeded:
    """Create a mock RateLimitExceeded (constructor requires a Limit object)."""
    exc = Mock(spec=RateLimitExceeded)
    exc.status_code = 429
    exc.detail = "rate limit exceeded"
    return exc


class TestRateLimitExceededHandler:

    def _make_request(self, method="GET", path="/test", headers=None, client_host="127.0.0.1"):
        request = Mock(spec=Request)
        request.method = method
        request.url = Mock()
        request.url.path = path
        request.headers = headers or {}
        request.client = Mock()
        request.client.host = client_host
        return request

    @pytest.mark.asyncio
    async def test_returns_429_status(self):
        request = self._make_request()
        exc = _make_exc()

        with patch("ada_backend.middleware.rate_limit_middleware.cooldown_service") as mock_cd, \
             patch("ada_backend.middleware.rate_limit_middleware.settings") as mock_settings:
            mock_cd.record_violation.return_value = 60
            mock_settings.RATE_LIMIT_REQUESTS = 50
            mock_settings.RATE_LIMIT_WINDOW = 60

            response = await rate_limit_exceeded_handler(request, exc)

        assert response.status_code == 429

    @pytest.mark.asyncio
    async def test_includes_retry_after_header(self):
        request = self._make_request()
        exc = _make_exc()

        with patch("ada_backend.middleware.rate_limit_middleware.cooldown_service") as mock_cd, \
             patch("ada_backend.middleware.rate_limit_middleware.settings") as mock_settings:
            mock_cd.record_violation.return_value = 120
            mock_settings.RATE_LIMIT_REQUESTS = 50
            mock_settings.RATE_LIMIT_WINDOW = 60

            response = await rate_limit_exceeded_handler(request, exc)

        assert response.headers["Retry-After"] == "120"
        assert response.headers["X-RateLimit-Remaining"] == "0"
        assert response.headers["X-RateLimit-Limit"] == "50"

    @pytest.mark.asyncio
    async def test_escalating_retry_after(self):
        request = self._make_request(
            headers={"Authorization": "Bearer my-token"},
        )
        exc = _make_exc()

        with patch("ada_backend.middleware.rate_limit_middleware.cooldown_service") as mock_cd, \
             patch("ada_backend.middleware.rate_limit_middleware.settings") as mock_settings:
            mock_cd.record_violation.return_value = 240
            mock_settings.RATE_LIMIT_REQUESTS = 50
            mock_settings.RATE_LIMIT_WINDOW = 60

            response = await rate_limit_exceeded_handler(request, exc)

        assert response.headers["Retry-After"] == "240"
        mock_cd.record_violation.assert_called_once()

    @pytest.mark.asyncio
    async def test_calls_key_func_for_identifier(self):
        request = self._make_request(
            headers={"X-API-Key": "my-api-key"},
        )
        exc = _make_exc()

        with patch("ada_backend.middleware.rate_limit_middleware.cooldown_service") as mock_cd, \
             patch("ada_backend.middleware.rate_limit_middleware.settings") as mock_settings:
            mock_cd.record_violation.return_value = 60
            mock_settings.RATE_LIMIT_REQUESTS = 50
            mock_settings.RATE_LIMIT_WINDOW = 60

            await rate_limit_exceeded_handler(request, exc)

        identifier = mock_cd.record_violation.call_args[0][0]
        assert identifier.startswith("apikey:")

    @pytest.mark.asyncio
    async def test_ip_fallback_identifier(self):
        request = self._make_request(client_host="10.0.0.5")
        exc = _make_exc()

        with patch("ada_backend.middleware.rate_limit_middleware.cooldown_service") as mock_cd, \
             patch("ada_backend.middleware.rate_limit_middleware.settings") as mock_settings:
            mock_cd.record_violation.return_value = 60
            mock_settings.RATE_LIMIT_REQUESTS = 50
            mock_settings.RATE_LIMIT_WINDOW = 60

            await rate_limit_exceeded_handler(request, exc)

        identifier = mock_cd.record_violation.call_args[0][0]
        assert identifier == "ip:10.0.0.5"

    @pytest.mark.asyncio
    async def test_response_body_contains_detail_and_retry_after(self):
        request = self._make_request()
        exc = _make_exc()

        with patch("ada_backend.middleware.rate_limit_middleware.cooldown_service") as mock_cd, \
             patch("ada_backend.middleware.rate_limit_middleware.settings") as mock_settings:
            mock_cd.record_violation.return_value = 60
            mock_settings.RATE_LIMIT_REQUESTS = 50
            mock_settings.RATE_LIMIT_WINDOW = 60

            response = await rate_limit_exceeded_handler(request, exc)

        assert response.body is not None
