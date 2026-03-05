import base64
import hashlib
import json
import logging

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from ada_backend.services.rate_limit_service import check_rate_limit
from settings import settings

LOGGER = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.exempted_paths = self._parse_exempted_paths()
        LOGGER.info(f"Rate limit middleware initialized. Exempted paths: {self.exempted_paths}")

    def _parse_exempted_paths(self) -> set[str]:
        if not settings.RATE_LIMIT_EXEMPTED_PATHS:
            return set()

        paths = settings.RATE_LIMIT_EXEMPTED_PATHS.split(",")
        return {path.strip() for path in paths if path.strip()}

    def _get_client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()

        if request.client:
            return request.client.host

        return "unknown"

    def _extract_user_id_from_jwt(self, token: str) -> str | None:
        """
        Decode the JWT payload to extract the subject (user ID) without
        full signature validation. This is safe for rate-limiting because
        we only need a stable per-user identifier, not proof of identity
        (authentication still happens later in the endpoint dependencies).
        """
        try:
            payload_b64 = token.split(".")[1]
            # JWT uses URL-safe base64 without padding
            padding = 4 - len(payload_b64) % 4
            if padding != 4:
                payload_b64 += "=" * padding
            payload = json.loads(base64.urlsafe_b64decode(payload_b64))
            user_id = payload.get("sub")
            if user_id:
                return str(user_id)
        except Exception:
            pass
        return None

    def _extract_identifier(self, request: Request) -> str:
        """
        Build a rate-limit key from the request.

        Priority:
          1. JWT → extract real user ID from the `sub` claim
          2. API key headers → hash-based identifier
          3. Client IP (fallback for unauthenticated requests)
        """
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]
            user_id = self._extract_user_id_from_jwt(token)
            if user_id:
                return f"user:{user_id}"
            token_hash = hashlib.sha256(token.encode()).hexdigest()[:16]
            return f"token:{token_hash}"

        api_key_headers = [
            "X-API-Key",
            "X-Ingestion-API-Key",
            "X-Webhook-API-Key",
            "X-Admin-API-Key",
        ]

        for header_name in api_key_headers:
            api_key = request.headers.get(header_name)
            if api_key:
                key_hash = hashlib.sha256(api_key.encode()).hexdigest()[:16]
                return f"apikey:{key_hash}"

        client_ip = self._get_client_ip(request)
        return f"ip:{client_ip}"

    def _is_path_exempted(self, path: str) -> bool:
        return path in self.exempted_paths

    async def dispatch(self, request: Request, call_next) -> Response:
        if not settings.RATE_LIMIT_ENABLED:
            return await call_next(request)

        if self._is_path_exempted(request.url.path):
            return await call_next(request)

        identifier = self._extract_identifier(request)

        is_allowed, retry_after, remaining = check_rate_limit(
            identifier=identifier,
            limit=settings.RATE_LIMIT_REQUESTS,
            window=settings.RATE_LIMIT_WINDOW,
        )

        if not is_allowed:
            LOGGER.warning(f"Rate limit exceeded for {identifier} on {request.method} {request.url.path}")

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

        response = await call_next(request)

        response.headers["X-RateLimit-Limit"] = str(settings.RATE_LIMIT_REQUESTS)
        response.headers["X-RateLimit-Remaining"] = str(remaining)

        return response
