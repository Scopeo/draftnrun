import hashlib
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi import Request

from ada_backend.services.rate_limit_service import (
    ProgressiveCooldownService,
    key_func,
)

# ---------------------------------------------------------------------------
# key_func tests
# ---------------------------------------------------------------------------


class TestKeyFunc:

    def _make_request(self, headers=None, client_host="127.0.0.1"):
        request = Mock(spec=Request)
        request.headers = headers or {}
        request.client = Mock()
        request.client.host = client_host
        return request

    def test_bearer_token_produces_token_hash(self):
        token = "some-jwt-token-value"
        request = self._make_request(headers={"Authorization": f"Bearer {token}"})
        expected_hash = hashlib.sha256(token.encode()).hexdigest()[:16]

        result = key_func(request)
        assert result == f"token:{expected_hash}"

    def test_different_tokens_produce_different_keys(self):
        r1 = self._make_request(headers={"Authorization": "Bearer token-aaa"})
        r2 = self._make_request(headers={"Authorization": "Bearer token-bbb"})

        assert key_func(r1) != key_func(r2)

    def test_api_key_header(self):
        api_key = "my-secret-api-key"
        request = self._make_request(headers={"X-API-Key": api_key})
        expected_hash = hashlib.sha256(api_key.encode()).hexdigest()[:16]

        result = key_func(request)
        assert result == f"apikey:{expected_hash}"

    def test_ingestion_api_key_header(self):
        request = self._make_request(headers={"X-Ingestion-API-Key": "ingestion-key"})
        result = key_func(request)
        assert result.startswith("apikey:")

    def test_webhook_api_key_header(self):
        request = self._make_request(headers={"X-Webhook-API-Key": "webhook-key"})
        result = key_func(request)
        assert result.startswith("apikey:")

    def test_admin_api_key_header(self):
        request = self._make_request(headers={"X-Admin-API-Key": "admin-key"})
        result = key_func(request)
        assert result.startswith("apikey:")

    def test_bearer_takes_priority_over_api_key(self):
        request = self._make_request(
            headers={
                "Authorization": "Bearer some-token",
                "X-API-Key": "some-api-key",
            }
        )
        result = key_func(request)
        assert result.startswith("token:")

    def test_falls_back_to_ip(self):
        request = self._make_request(client_host="10.0.0.5")
        result = key_func(request)
        assert result == "ip:10.0.0.5"

    def test_x_forwarded_for_used_for_ip(self):
        request = self._make_request(
            headers={"X-Forwarded-For": "203.0.113.1, 198.51.100.1"},
            client_host="10.0.0.1",
        )
        result = key_func(request)
        assert result == "ip:203.0.113.1"

    def test_no_client_returns_unknown(self):
        request = self._make_request()
        request.client = None
        result = key_func(request)
        assert result == "ip:unknown"

    def test_authorization_header_without_bearer_falls_back_to_ip(self):
        request = self._make_request(
            headers={"Authorization": "Basic abc123"},
            client_host="1.2.3.4",
        )
        result = key_func(request)
        assert result == "ip:1.2.3.4"


# ---------------------------------------------------------------------------
# ProgressiveCooldownService tests
# ---------------------------------------------------------------------------


class TestProgressiveCooldownService:

    @pytest.fixture
    def mock_redis(self):
        return MagicMock()

    @pytest.fixture
    def service(self):
        return ProgressiveCooldownService()

    def test_first_violation_returns_base_window(self, service, mock_redis):
        mock_redis.get.return_value = None

        with patch.object(service, "_get_pool", return_value=MagicMock()), \
             patch("ada_backend.services.rate_limit_service.redis.Redis", return_value=mock_redis), \
             patch("ada_backend.services.rate_limit_service.settings") as mock_settings:
            mock_settings.RATE_LIMIT_WINDOW = 60
            mock_settings.RATE_LIMIT_PROGRESSIVE_COOLDOWN = True
            mock_settings.RATE_LIMIT_COOLDOWN_MULTIPLIER = 2.0
            mock_settings.RATE_LIMIT_COOLDOWN_MAX = 3600

            retry_after = service.record_violation("user:123")

        assert retry_after == 60

    def test_second_violation_doubles(self, service, mock_redis):
        mock_redis.get.return_value = "1"

        with patch.object(service, "_get_pool", return_value=MagicMock()), \
             patch("ada_backend.services.rate_limit_service.redis.Redis", return_value=mock_redis), \
             patch("ada_backend.services.rate_limit_service.settings") as mock_settings:
            mock_settings.RATE_LIMIT_WINDOW = 60
            mock_settings.RATE_LIMIT_PROGRESSIVE_COOLDOWN = True
            mock_settings.RATE_LIMIT_COOLDOWN_MULTIPLIER = 2.0
            mock_settings.RATE_LIMIT_COOLDOWN_MAX = 3600

            retry_after = service.record_violation("user:123")

        assert retry_after == 120

    def test_third_violation_quadruples(self, service, mock_redis):
        mock_redis.get.return_value = "2"

        with patch.object(service, "_get_pool", return_value=MagicMock()), \
             patch("ada_backend.services.rate_limit_service.redis.Redis", return_value=mock_redis), \
             patch("ada_backend.services.rate_limit_service.settings") as mock_settings:
            mock_settings.RATE_LIMIT_WINDOW = 60
            mock_settings.RATE_LIMIT_PROGRESSIVE_COOLDOWN = True
            mock_settings.RATE_LIMIT_COOLDOWN_MULTIPLIER = 2.0
            mock_settings.RATE_LIMIT_COOLDOWN_MAX = 3600

            retry_after = service.record_violation("user:123")

        assert retry_after == 240

    def test_respects_max_cooldown(self, service, mock_redis):
        mock_redis.get.return_value = "10"

        with patch.object(service, "_get_pool", return_value=MagicMock()), \
             patch("ada_backend.services.rate_limit_service.redis.Redis", return_value=mock_redis), \
             patch("ada_backend.services.rate_limit_service.settings") as mock_settings:
            mock_settings.RATE_LIMIT_WINDOW = 60
            mock_settings.RATE_LIMIT_PROGRESSIVE_COOLDOWN = True
            mock_settings.RATE_LIMIT_COOLDOWN_MULTIPLIER = 2.0
            mock_settings.RATE_LIMIT_COOLDOWN_MAX = 600

            retry_after = service.record_violation("user:123")

        assert retry_after == 600

    def test_stores_violation_count_in_redis(self, service, mock_redis):
        mock_redis.get.return_value = "2"

        with patch.object(service, "_get_pool", return_value=MagicMock()), \
             patch("ada_backend.services.rate_limit_service.redis.Redis", return_value=mock_redis), \
             patch("ada_backend.services.rate_limit_service.settings") as mock_settings:
            mock_settings.RATE_LIMIT_WINDOW = 60
            mock_settings.RATE_LIMIT_PROGRESSIVE_COOLDOWN = True
            mock_settings.RATE_LIMIT_COOLDOWN_MULTIPLIER = 2.0
            mock_settings.RATE_LIMIT_COOLDOWN_MAX = 3600

            service.record_violation("user:123")

        mock_redis.setex.assert_called_once()
        key, ttl, count = mock_redis.setex.call_args[0]
        assert key == "rate_limit:violations:user:123"
        assert count == 3

    def test_disabled_returns_base_window(self, service):
        with patch("ada_backend.services.rate_limit_service.settings") as mock_settings:
            mock_settings.RATE_LIMIT_WINDOW = 60
            mock_settings.RATE_LIMIT_PROGRESSIVE_COOLDOWN = False

            retry_after = service.record_violation("user:123")

        assert retry_after == 60

    def test_redis_unavailable_returns_base_window(self, service):
        with patch.object(service, "_get_pool", return_value=None), \
             patch("ada_backend.services.rate_limit_service.settings") as mock_settings:
            mock_settings.RATE_LIMIT_WINDOW = 60
            mock_settings.RATE_LIMIT_PROGRESSIVE_COOLDOWN = True

            retry_after = service.record_violation("user:123")

        assert retry_after == 60

    def test_redis_error_returns_base_window(self, service, mock_redis):
        mock_redis.get.side_effect = Exception("Redis error")

        with patch.object(service, "_get_pool", return_value=MagicMock()), \
             patch("ada_backend.services.rate_limit_service.redis.Redis", return_value=mock_redis), \
             patch("ada_backend.services.rate_limit_service.settings") as mock_settings:
            mock_settings.RATE_LIMIT_WINDOW = 60
            mock_settings.RATE_LIMIT_PROGRESSIVE_COOLDOWN = True

            retry_after = service.record_violation("user:123")

        assert retry_after == 60
