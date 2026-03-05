import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from ada_backend.services.rate_limit_service import cooldown_service, key_func
from settings import settings

LOGGER = logging.getLogger(__name__)


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """
    Custom handler for slowapi's RateLimitExceeded exception.

    When progressive cooldown is enabled, escalates retry-after for
    repeat violators using the ProgressiveCooldownService.
    """
    identifier = key_func(request)
    retry_after = cooldown_service.record_violation(identifier)

    LOGGER.warning(
        f"Rate limit exceeded for {identifier} on "
        f"{request.method} {request.url.path}"
    )

    return JSONResponse(
        status_code=429,
        content={
            "detail": (
                f"Rate limit exceeded. Maximum {settings.RATE_LIMIT_REQUESTS} "
                f"requests per {settings.RATE_LIMIT_WINDOW} seconds."
            ),
            "retry_after": retry_after,
        },
        headers={
            "Retry-After": str(retry_after),
            "X-RateLimit-Limit": str(settings.RATE_LIMIT_REQUESTS),
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": str(retry_after),
        },
    )
