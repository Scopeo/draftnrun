"""Best-effort redaction helpers for Sentry events and untyped span attributes.

This is defense-in-depth only. The primary boundary for secrets is
``pydantic.SecretStr`` typing + explicit unwrap at the execution boundary, with
``engine/trace/serializer.py`` masking any ``SecretStr`` that reaches a span or
log.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import SecretStr

REDACTED_PLACEHOLDER = "[REDACTED]"

SENSITIVE_FIELD_MARKERS: tuple[str, ...] = (
    "api_key",
    "apikey",
    "authorization",
    "bearer",
    "client_secret",
    "cookie",
    "credential",
    "jwt",
    "password",
    "passwd",
    "private_key",
    "refresh_token",
    "secret",
    "session_key",
    "token",
)

_BEARER_TOKEN_RE = re.compile(r"Bearer\s+[A-Za-z0-9._\-+/=]+", re.IGNORECASE)


def _normalize_key(key: str | None) -> str:
    return (key or "").lower().replace("-", "_")


def is_sensitive_key(key: str | None) -> bool:
    normalized = _normalize_key(key)
    if not normalized:
        return False
    return any(marker in normalized for marker in SENSITIVE_FIELD_MARKERS)


def redact_sensitive(value: Any, key: str | None = None) -> Any:
    """Recursively redact values whose key matches a sensitive marker."""
    if isinstance(value, SecretStr):
        return REDACTED_PLACEHOLDER

    if is_sensitive_key(key):
        return REDACTED_PLACEHOLDER

    if isinstance(value, dict):
        return {item_key: redact_sensitive(item_value, str(item_key)) for item_key, item_value in value.items()}

    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]

    if isinstance(value, tuple):
        return tuple(redact_sensitive(item) for item in value)

    if isinstance(value, set):
        return {redact_sensitive(item) for item in value}

    if isinstance(value, str):
        return _BEARER_TOKEN_RE.sub(f"Bearer {REDACTED_PLACEHOLDER}", value)

    return value


def redact_mapping(mapping: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(mapping, dict):
        raise TypeError(f"redact_mapping expects dict, got {type(mapping).__name__}")
    return redact_sensitive(mapping)  # type: ignore[return-value]


def scrub_sentry_event(event: Any) -> Any:
    """``before_send`` / ``before_send_log`` / ``before_send_transaction`` hook."""
    return redact_sensitive(event)
