import time
from unittest.mock import MagicMock, patch

import pytest

from ada_backend.services.rate_limit_service import RateLimitService, check_rate_limit


class TestRateLimitService:

    @pytest.fixture
    def mock_redis(self):
        redis_mock = MagicMock()
        redis_mock.pipeline.return_value = redis_mock
        redis_mock.execute.return_value = [None, 0]
        redis_mock.zrange.return_value = []
        return redis_mock

    @pytest.fixture
    def service(self):
        return RateLimitService()

    def test_allows_first_request(self, service, mock_redis):
        with patch("ada_backend.services.rate_limit_service.get_redis_client", return_value=mock_redis):
            service._redis_client = None
            is_allowed, retry_after, remaining = service.check_rate_limit("user:123", limit=10, window=60)

            assert is_allowed is True
            assert retry_after == 0
            assert remaining == 9

    def test_enforces_limit(self, service, mock_redis):
        mock_redis.execute.return_value = [None, 10]
        mock_redis.get.return_value = None

        with (
            patch("ada_backend.services.rate_limit_service.get_redis_client", return_value=mock_redis),
            patch("ada_backend.services.rate_limit_service.settings") as mock_settings,
        ):
            mock_settings.RATE_LIMIT_PROGRESSIVE_COOLDOWN = True
            mock_settings.RATE_LIMIT_COOLDOWN_MULTIPLIER = 2.0
            mock_settings.RATE_LIMIT_COOLDOWN_MAX = 3600
            service._redis_client = None
            is_allowed, retry_after, remaining = service.check_rate_limit("user:123", limit=10, window=60)

            assert is_allowed is False
            assert retry_after == 60
            assert remaining == 0

    def test_under_limit(self, service, mock_redis):
        mock_redis.execute.return_value = [None, 5]

        with patch("ada_backend.services.rate_limit_service.get_redis_client", return_value=mock_redis):
            service._redis_client = None
            is_allowed, retry_after, remaining = service.check_rate_limit("user:123", limit=10, window=60)

            assert is_allowed is True
            assert retry_after == 0
            assert remaining == 4
            mock_redis.zadd.assert_called_once()

    def test_redis_unavailable_fails_open(self, service):
        with patch("ada_backend.services.rate_limit_service.get_redis_client", return_value=None):
            service._redis_client = None
            is_allowed, retry_after, remaining = service.check_rate_limit("user:123", limit=10, window=60)

            assert is_allowed is True
            assert retry_after == 0
            assert remaining == 10

    def test_redis_error_fails_open_and_invalidates_client(self, service, mock_redis):
        mock_redis.pipeline.side_effect = Exception("Redis connection error")

        with patch("ada_backend.services.rate_limit_service.get_redis_client", return_value=mock_redis):
            service._redis_client = None
            is_allowed, retry_after, remaining = service.check_rate_limit("user:123", limit=10, window=60)

            assert is_allowed is True
            assert retry_after == 0
            assert remaining == 10
            # Client should be invalidated so next call triggers reconnect
            assert service._redis_client is None

    def test_uses_settings_defaults(self, service, mock_redis):
        mock_redis.execute.return_value = [None, 0]

        with (
            patch("ada_backend.services.rate_limit_service.get_redis_client", return_value=mock_redis),
            patch("ada_backend.services.rate_limit_service.settings") as mock_settings,
        ):
            mock_settings.RATE_LIMIT_REQUESTS = 50
            mock_settings.RATE_LIMIT_WINDOW = 60
            service._redis_client = None

            is_allowed, _, _ = service.check_rate_limit("user:123")

            assert is_allowed is True

    def test_different_users_independent(self, service, mock_redis):
        mock_redis.execute.return_value = [None, 0]

        with patch("ada_backend.services.rate_limit_service.get_redis_client", return_value=mock_redis):
            service._redis_client = None

            service.check_rate_limit("user:123", limit=10, window=60)
            service.check_rate_limit("user:456", limit=10, window=60)

            assert mock_redis.pipeline.call_count >= 2

    def test_remaining_never_negative(self, service, mock_redis):
        mock_redis.execute.return_value = [None, 15]
        mock_redis.get.return_value = None

        with (
            patch("ada_backend.services.rate_limit_service.get_redis_client", return_value=mock_redis),
            patch("ada_backend.services.rate_limit_service.settings") as mock_settings,
        ):
            mock_settings.RATE_LIMIT_PROGRESSIVE_COOLDOWN = True
            mock_settings.RATE_LIMIT_COOLDOWN_MULTIPLIER = 2.0
            mock_settings.RATE_LIMIT_COOLDOWN_MAX = 3600
            service._redis_client = None
            _, _, remaining = service.check_rate_limit("user:123", limit=10, window=60)

            assert remaining == 0

    def test_removes_old_entries(self, service, mock_redis):
        mock_redis.execute.return_value = [None, 5]

        with patch("ada_backend.services.rate_limit_service.get_redis_client", return_value=mock_redis):
            service._redis_client = None
            service.check_rate_limit("user:123", limit=10, window=60)

            pipeline_calls = mock_redis.method_calls
            zremrangebyscore_called = any("zremrangebyscore" in str(call) for call in pipeline_calls)
            assert zremrangebyscore_called

    def test_sets_expiration(self, service, mock_redis):
        mock_redis.execute.return_value = [None, 5]

        with patch("ada_backend.services.rate_limit_service.get_redis_client", return_value=mock_redis):
            service._redis_client = None
            service.check_rate_limit("user:123", limit=10, window=60)

            mock_redis.expire.assert_called_once()
            call_args = mock_redis.expire.call_args
            assert "rate_limit:user:123" in call_args[0]


def test_module_check_rate_limit():
    with patch("ada_backend.services.rate_limit_service._rate_limit_service") as mock_service:
        mock_service.check_rate_limit.return_value = (True, 0, 49)

        is_allowed, retry_after, remaining = check_rate_limit("user:123", limit=10, window=60)

        assert is_allowed is True
        assert retry_after == 0
        assert remaining == 49
        mock_service.check_rate_limit.assert_called_once_with("user:123", 10, 60)


class TestProgressiveCooldown:

    @pytest.fixture
    def mock_redis(self):
        redis_mock = MagicMock()
        redis_mock.pipeline.return_value = redis_mock
        redis_mock.execute.return_value = [None, 10]
        redis_mock.zrange.return_value = [(b"old", time.time() - 30)]
        redis_mock.get.return_value = None
        return redis_mock

    @pytest.fixture
    def service(self):
        return RateLimitService()

    def test_first_violation(self, service, mock_redis):
        mock_redis.get.return_value = None

        with (
            patch("ada_backend.services.rate_limit_service.get_redis_client", return_value=mock_redis),
            patch("ada_backend.services.rate_limit_service.settings") as mock_settings,
        ):
            mock_settings.RATE_LIMIT_PROGRESSIVE_COOLDOWN = True
            mock_settings.RATE_LIMIT_COOLDOWN_MULTIPLIER = 2.0
            mock_settings.RATE_LIMIT_COOLDOWN_MAX = 3600
            service._redis_client = None

            is_allowed, retry_after, _ = service.check_rate_limit("user:123", limit=10, window=60)

            assert is_allowed is False
            assert retry_after == 60

    def test_second_violation(self, service, mock_redis):
        mock_redis.get.return_value = b"1"

        with (
            patch("ada_backend.services.rate_limit_service.get_redis_client", return_value=mock_redis),
            patch("ada_backend.services.rate_limit_service.settings") as mock_settings,
        ):
            mock_settings.RATE_LIMIT_PROGRESSIVE_COOLDOWN = True
            mock_settings.RATE_LIMIT_COOLDOWN_MULTIPLIER = 2.0
            mock_settings.RATE_LIMIT_COOLDOWN_MAX = 3600
            service._redis_client = None

            is_allowed, retry_after, _ = service.check_rate_limit("user:123", limit=10, window=60)

            assert is_allowed is False
            assert retry_after == 120

    def test_third_violation(self, service, mock_redis):
        mock_redis.get.return_value = b"2"

        with (
            patch("ada_backend.services.rate_limit_service.get_redis_client", return_value=mock_redis),
            patch("ada_backend.services.rate_limit_service.settings") as mock_settings,
        ):
            mock_settings.RATE_LIMIT_PROGRESSIVE_COOLDOWN = True
            mock_settings.RATE_LIMIT_COOLDOWN_MULTIPLIER = 2.0
            mock_settings.RATE_LIMIT_COOLDOWN_MAX = 3600
            service._redis_client = None

            is_allowed, retry_after, _ = service.check_rate_limit("user:123", limit=10, window=60)

            assert is_allowed is False
            assert retry_after == 240

    def test_respects_max(self, service, mock_redis):
        mock_redis.get.return_value = b"10"

        with (
            patch("ada_backend.services.rate_limit_service.get_redis_client", return_value=mock_redis),
            patch("ada_backend.services.rate_limit_service.settings") as mock_settings,
        ):
            mock_settings.RATE_LIMIT_PROGRESSIVE_COOLDOWN = True
            mock_settings.RATE_LIMIT_COOLDOWN_MULTIPLIER = 2.0
            mock_settings.RATE_LIMIT_COOLDOWN_MAX = 600
            service._redis_client = None

            is_allowed, retry_after, _ = service.check_rate_limit("user:123", limit=10, window=60)

            assert is_allowed is False
            assert retry_after == 600

    def test_disabled(self, service, mock_redis):
        mock_redis.get.return_value = b"5"

        with (
            patch("ada_backend.services.rate_limit_service.get_redis_client", return_value=mock_redis),
            patch("ada_backend.services.rate_limit_service.settings") as mock_settings,
        ):
            mock_settings.RATE_LIMIT_PROGRESSIVE_COOLDOWN = False
            service._redis_client = None

            is_allowed, retry_after, _ = service.check_rate_limit("user:123", limit=10, window=60)

            assert is_allowed is False
            assert retry_after <= 60

    def test_stores_violation_count(self, service, mock_redis):
        mock_redis.get.return_value = b"2"

        with (
            patch("ada_backend.services.rate_limit_service.get_redis_client", return_value=mock_redis),
            patch("ada_backend.services.rate_limit_service.settings") as mock_settings,
        ):
            mock_settings.RATE_LIMIT_PROGRESSIVE_COOLDOWN = True
            mock_settings.RATE_LIMIT_COOLDOWN_MULTIPLIER = 2.0
            mock_settings.RATE_LIMIT_COOLDOWN_MAX = 3600
            service._redis_client = None

            service.check_rate_limit("user:123", limit=10, window=60)

            mock_redis.setex.assert_called_once()
            call_args = mock_redis.setex.call_args[0]
            assert "rate_limit:violations:user:123" in call_args[0]
            assert call_args[2] == 3
