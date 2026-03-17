import logging
import os
import subprocess

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

LOGGER = logging.getLogger(__name__)

_RSS_SPIKE_THRESHOLD_MB = 10
_PID = str(os.getpid())


def _get_current_rss_mb() -> float:
    """Return current RSS in MB via ps (not peak)."""
    try:
        out = subprocess.check_output(["ps", "-o", "rss=", "-p", _PID]).strip()
        return int(out) / 1024
    except Exception:
        return 0.0


class MemoryTrackingMiddleware(BaseHTTPMiddleware):
    """Logs any request that increases RSS by more than 10 MB."""

    async def dispatch(self, request: Request, call_next) -> Response:
        rss_before = _get_current_rss_mb()
        response = await call_next(request)
        rss_after = _get_current_rss_mb()

        delta = rss_after - rss_before
        if delta > _RSS_SPIKE_THRESHOLD_MB:
            LOGGER.warning(
                "MEMORY_SPIKE: %s %s +%.0fMB (%.0fMB -> %.0fMB)",
                request.method,
                request.url.path,
                delta,
                rss_before,
                rss_after,
            )

        return response
