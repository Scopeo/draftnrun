import base64
import json
from unittest.mock import Mock, patch

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ada_backend.middleware.rate_limit_middleware import RateLimitMiddleware


@pytest.fixture
def app():
    test_app = FastAPI()

    @test_app.get("/test")
    def test_endpoint():
        return {"message": "success"}

    @test_app.get("/health")
    def health_endpoint():
        return {"status": "ok"}

    return test_app


@pytest.fixture
def middleware(app):
    return RateLimitMiddleware(app)


@pytest.fixture
def mock_request():
    request = Mock(spec=Request)
    request.url.path = "/test"
    request.method = "GET"
    request.headers = {}
    request.client = Mock()
    request.client.host = "127.0.0.1"
    return request


@pytest.fixture
def mock_call_next():
    async def call_next(request):
        return JSONResponse(content={"message": "success"})

    return call_next


def _make_jwt(sub: str) -> str:
    """Build a minimal unsigned JWT with the given subject claim."""
    header = base64.urlsafe_b64encode(json.dumps({"alg": "none"}).encode()).rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(json.dumps({"sub": sub}).encode()).rstrip(b"=").decode()
    return f"{header}.{payload}.signature"


class TestRateLimitMiddleware:

    def test_init_parses_exempted_paths(self, app):
        with patch("ada_backend.middleware.rate_limit_middleware.settings") as mock_settings:
            mock_settings.RATE_LIMIT_EXEMPTED_PATHS = "/health,/metrics,/"
            mw = RateLimitMiddleware(app)

            assert "/health" in mw.exempted_paths
            assert "/metrics" in mw.exempted_paths
            assert "/" in mw.exempted_paths

    def test_get_client_ip_from_forwarded_header(self, middleware, mock_request):
        mock_request.headers = {"X-Forwarded-For": "203.0.113.1, 198.51.100.1"}
        assert middleware._get_client_ip(mock_request) == "203.0.113.1"

    def test_get_client_ip_from_client(self, middleware, mock_request):
        assert middleware._get_client_ip(mock_request) == "127.0.0.1"

    def test_get_client_ip_no_client(self, middleware, mock_request):
        mock_request.client = None
        assert middleware._get_client_ip(mock_request) == "unknown"

    # ---- identifier extraction ----

    def test_extract_identifier_from_jwt_sub(self, middleware, mock_request):
        """JWT with a valid sub claim should produce a user:<id> key."""
        token = _make_jwt("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
        mock_request.headers = {"Authorization": f"Bearer {token}"}

        identifier = middleware._extract_identifier(mock_request)
        assert identifier == "user:aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

    def test_extract_identifier_from_malformed_jwt_falls_back_to_hash(self, middleware, mock_request):
        """A token that is not valid JSON falls back to token:<hash>."""
        mock_request.headers = {"Authorization": "Bearer not-a-real-jwt"}

        identifier = middleware._extract_identifier(mock_request)
        assert identifier.startswith("token:")

    def test_extract_identifier_from_api_key(self, middleware, mock_request):
        mock_request.headers = {"X-API-Key": "test_api_key_12345"}

        identifier = middleware._extract_identifier(mock_request)
        assert identifier.startswith("apikey:")

    def test_extract_identifier_fallback_to_ip(self, middleware, mock_request):
        identifier = middleware._extract_identifier(mock_request)
        assert identifier == "ip:127.0.0.1"

    def test_is_path_exempted(self, middleware):
        middleware.exempted_paths = {"/health", "/metrics"}

        assert middleware._is_path_exempted("/health") is True
        assert middleware._is_path_exempted("/metrics") is True
        assert middleware._is_path_exempted("/api/test") is False

    # ---- dispatch tests ----

    @pytest.mark.asyncio
    async def test_dispatch_disabled_bypasses_limit(self, middleware, mock_request, mock_call_next):
        with patch("ada_backend.middleware.rate_limit_middleware.settings") as mock_settings:
            mock_settings.RATE_LIMIT_ENABLED = False

            response = await middleware.dispatch(mock_request, mock_call_next)

            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_dispatch_exempted_path_bypasses_limit(self, middleware, mock_request, mock_call_next):
        mock_request.url.path = "/health"
        middleware.exempted_paths = {"/health"}

        with patch("ada_backend.middleware.rate_limit_middleware.settings") as mock_settings:
            mock_settings.RATE_LIMIT_ENABLED = True

            response = await middleware.dispatch(mock_request, mock_call_next)

            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_dispatch_allows_request_under_limit(self, middleware, mock_request, mock_call_next):
        with (
            patch("ada_backend.middleware.rate_limit_middleware.settings") as mock_settings,
            patch("ada_backend.middleware.rate_limit_middleware.check_rate_limit") as mock_check,
        ):
            mock_settings.RATE_LIMIT_ENABLED = True
            mock_settings.RATE_LIMIT_REQUESTS = 50
            mock_settings.RATE_LIMIT_WINDOW = 60
            mock_check.return_value = (True, 0, 49)
            middleware.exempted_paths = set()

            response = await middleware.dispatch(mock_request, mock_call_next)

            assert response.status_code == 200
            assert response.headers["X-RateLimit-Limit"] == "50"
            assert response.headers["X-RateLimit-Remaining"] == "49"

    @pytest.mark.asyncio
    async def test_dispatch_rejects_request_over_limit(self, middleware, mock_request, mock_call_next):
        with (
            patch("ada_backend.middleware.rate_limit_middleware.settings") as mock_settings,
            patch("ada_backend.middleware.rate_limit_middleware.check_rate_limit") as mock_check,
        ):
            mock_settings.RATE_LIMIT_ENABLED = True
            mock_settings.RATE_LIMIT_REQUESTS = 50
            mock_settings.RATE_LIMIT_WINDOW = 60
            mock_check.return_value = (False, 30, 0)
            middleware.exempted_paths = set()

            response = await middleware.dispatch(mock_request, mock_call_next)

            assert response.status_code == 429
            assert response.headers["Retry-After"] == "30"
            assert response.headers["X-RateLimit-Remaining"] == "0"

    @pytest.mark.asyncio
    async def test_dispatch_adds_rate_limit_headers(self, middleware, mock_request, mock_call_next):
        with (
            patch("ada_backend.middleware.rate_limit_middleware.settings") as mock_settings,
            patch("ada_backend.middleware.rate_limit_middleware.check_rate_limit") as mock_check,
        ):
            mock_settings.RATE_LIMIT_ENABLED = True
            mock_settings.RATE_LIMIT_REQUESTS = 50
            mock_settings.RATE_LIMIT_WINDOW = 60
            mock_check.return_value = (True, 0, 25)
            middleware.exempted_paths = set()

            response = await middleware.dispatch(mock_request, mock_call_next)

            assert response.headers["X-RateLimit-Limit"] == "50"
            assert response.headers["X-RateLimit-Remaining"] == "25"

    @pytest.mark.asyncio
    async def test_dispatch_different_identifiers_separate_limits(self, middleware, mock_call_next):
        mock_request1 = Mock(spec=Request)
        mock_request1.url.path = "/test"
        mock_request1.method = "GET"
        mock_request1.headers = {"X-API-Key": "key1"}
        mock_request1.client = Mock()
        mock_request1.client.host = "127.0.0.1"

        mock_request2 = Mock(spec=Request)
        mock_request2.url.path = "/test"
        mock_request2.method = "GET"
        mock_request2.headers = {"X-API-Key": "key2"}
        mock_request2.client = Mock()
        mock_request2.client.host = "127.0.0.1"

        with (
            patch("ada_backend.middleware.rate_limit_middleware.settings") as mock_settings,
            patch("ada_backend.middleware.rate_limit_middleware.check_rate_limit") as mock_check,
        ):
            mock_settings.RATE_LIMIT_ENABLED = True
            mock_settings.RATE_LIMIT_REQUESTS = 50
            mock_settings.RATE_LIMIT_WINDOW = 60
            mock_check.return_value = (True, 0, 49)
            middleware.exempted_paths = set()

            await middleware.dispatch(mock_request1, mock_call_next)
            await middleware.dispatch(mock_request2, mock_call_next)

            assert mock_check.call_count == 2
            identifiers = [call[1]["identifier"] for call in mock_check.call_args_list]
            assert identifiers[0] != identifiers[1]
