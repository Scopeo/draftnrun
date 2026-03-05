import logging
import time
from typing import Optional
from uuid import uuid4

from ada_backend.utils.redis_client import get_redis_client
from settings import settings

LOGGER = logging.getLogger(__name__)


class RateLimitService:
    def __init__(self):
        self._redis_client: Optional[any] = None
        self._last_connection_attempt: float = 0
        self._connection_retry_delay: int = 5

    def _get_client(self):
        current_time = time.time()

        if self._redis_client is None:
            if current_time - self._last_connection_attempt < self._connection_retry_delay:
                return None

            self._last_connection_attempt = current_time
            try:
                self._redis_client = get_redis_client(decode_responses=False)
                if self._redis_client:
                    LOGGER.info("Rate limit service connected to Redis")
            except Exception as e:
                LOGGER.error(f"Failed to connect to Redis for rate limiting: {str(e)}")
                return None

        return self._redis_client

    def _invalidate_client(self):
        """Reset the cached Redis client so the next call triggers a reconnect."""
        self._redis_client = None

    def _calculate_retry_after(self, client, identifier: str, now: float, window: int) -> int:
        if not settings.RATE_LIMIT_PROGRESSIVE_COOLDOWN:
            key = f"rate_limit:{identifier}"
            oldest_timestamps = client.zrange(key, 0, 0, withscores=True)
            if oldest_timestamps:
                oldest_timestamp = oldest_timestamps[0][1]
                return int(oldest_timestamp + window - now) + 1
            return window

        violation_key = f"rate_limit:violations:{identifier}"

        try:
            violation_count = client.get(violation_key)
            if violation_count is None:
                violation_count = 0
            else:
                violation_count = int(violation_count)

            violation_count += 1

            base_retry = window
            multiplier = settings.RATE_LIMIT_COOLDOWN_MULTIPLIER
            max_cooldown = settings.RATE_LIMIT_COOLDOWN_MAX

            progressive_retry = int(base_retry * (multiplier ** (violation_count - 1)))
            retry_after = min(progressive_retry, max_cooldown)

            client.setex(violation_key, retry_after, violation_count)

            LOGGER.info(
                f"Progressive cooldown for {identifier}: violation #{violation_count}, "
                f"retry_after={retry_after}s (base={base_retry}s, multiplier={multiplier})"
            )

            return retry_after

        except Exception as e:
            LOGGER.error(f"Error calculating progressive cooldown: {str(e)}")
            return window

    def check_rate_limit(
        self,
        identifier: str,
        limit: Optional[int] = None,
        window: Optional[int] = None,
    ) -> tuple[bool, int, int]:
        """
        Check whether a request should be rate-limited.

        Returns:
            (is_allowed, retry_after_seconds, remaining_requests)
        """
        if limit is None:
            limit = settings.RATE_LIMIT_REQUESTS
        if window is None:
            window = settings.RATE_LIMIT_WINDOW

        client = self._get_client()

        if client is None:
            LOGGER.warning("Redis unavailable for rate limiting, allowing request (fail open)")
            return (True, 0, limit)

        try:
            key = f"rate_limit:{identifier}"
            now = time.time()
            window_start = now - window

            pipe = client.pipeline()
            pipe.zremrangebyscore(key, 0, window_start)
            pipe.zcount(key, window_start, now)
            results = pipe.execute()
            current_count = results[1]

            if current_count >= limit:
                retry_after = self._calculate_retry_after(client, identifier, now, window)

                LOGGER.warning(
                    f"Rate limit exceeded for {identifier}: {current_count}/{limit} "
                    f"requests in {window}s window, retry after {retry_after}s"
                )
                return (False, retry_after, 0)

            request_id = f"{now}:{uuid4()}"
            client.zadd(key, {request_id: now})
            client.expire(key, window + 60)

            remaining = max(0, limit - current_count - 1)
            return (True, 0, remaining)

        except Exception as e:
            self._invalidate_client()
            LOGGER.error(f"Error checking rate limit for {identifier}: {str(e)}", exc_info=True)
            return (True, 0, limit)


_rate_limit_service = RateLimitService()


def check_rate_limit(
    identifier: str,
    limit: Optional[int] = None,
    window: Optional[int] = None,
) -> tuple[bool, int, int]:
    """
    Check whether a request should be rate-limited.

    Returns:
        (is_allowed, retry_after_seconds, remaining_requests)
    """
    return _rate_limit_service.check_rate_limit(identifier, limit, window)
