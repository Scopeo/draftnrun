import hashlib
import logging
from typing import Optional

import redis
from fastapi import Request
from slowapi import Limiter

from settings import settings

LOGGER = logging.getLogger(__name__)


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def key_func(request: Request) -> str:

    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:]
        token_hash = hashlib.sha256(token.encode()).hexdigest()[:16]
        return f"token:{token_hash}"

    for header_name in (
        "X-API-Key",
        "X-Ingestion-API-Key",
        "X-Webhook-API-Key",
        "X-Admin-API-Key",
    ):
        value = request.headers.get(header_name)
        if value:
            key_hash = hashlib.sha256(value.encode()).hexdigest()[:16]
            return f"apikey:{key_hash}"

    return f"ip:{_get_client_ip(request)}"


def _build_storage_uri() -> str:
    """Build a Redis URI from settings for slowapi/limits storage."""
    host = settings.REDIS_HOST or "localhost"
    port = settings.REDIS_PORT or 6379
    password = settings.REDIS_PASSWORD
    if password:
        return f"redis://:{password}@{host}:{port}"
    return f"redis://{host}:{port}"


limiter = Limiter(
    key_func=key_func,
    default_limits=[f"{settings.RATE_LIMIT_REQUESTS}/{settings.RATE_LIMIT_WINDOW} second"],
    storage_uri=_build_storage_uri(),
    enabled=settings.RATE_LIMIT_ENABLED,
)


class ProgressiveCooldownService:
    def __init__(self):
        self._pool: Optional[redis.ConnectionPool] = None

    def _get_pool(self) -> Optional[redis.ConnectionPool]:
        if self._pool is None:
            if not settings.REDIS_HOST:
                return None
            try:
                self._pool = redis.ConnectionPool(
                    host=settings.REDIS_HOST,
                    port=settings.REDIS_PORT or 6379,
                    password=settings.REDIS_PASSWORD,
                    decode_responses=True,
                )
            except Exception as e:
                LOGGER.error(f"Failed to create Redis pool for cooldown: {e}")
                return None
        return self._pool

    def record_violation(self, identifier: str) -> int:

        base_window = settings.RATE_LIMIT_WINDOW

        if not settings.RATE_LIMIT_PROGRESSIVE_COOLDOWN:
            return base_window

        pool = self._get_pool()
        if pool is None:
            return base_window

        try:
            client = redis.Redis(connection_pool=pool)
            violation_key = f"rate_limit:violations:{identifier}"

            violation_count = client.get(violation_key)
            violation_count = int(violation_count) + 1 if violation_count else 1

            multiplier = settings.RATE_LIMIT_COOLDOWN_MULTIPLIER
            max_cooldown = settings.RATE_LIMIT_COOLDOWN_MAX

            retry_after = min(
                int(base_window * (multiplier ** (violation_count - 1))),
                max_cooldown,
            )

            client.setex(violation_key, retry_after, violation_count)

            LOGGER.info(
                f"Progressive cooldown for {identifier}: violation #{violation_count}, retry_after={retry_after}s"
            )
            return retry_after

        except Exception as e:
            LOGGER.error(f"Error recording violation for {identifier}: {e}")
            return base_window


cooldown_service = ProgressiveCooldownService()
