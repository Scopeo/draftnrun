import logging
import re
import time
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from ada_backend.repositories.global_secret_repository import (
    list_global_secrets,
    get_global_secret,
    upsert_global_secret,
    delete_global_secret,
)


LOGGER = logging.getLogger(__name__)


ENV_KEY_PATTERN = re.compile(r"^[A-Z_][A-Z0-9_]*$")


@dataclass
class _CacheEntry:
    value: Optional[str]
    expires_at: float


class GlobalSecretCache:
    def __init__(self, ttl_seconds: int = 60) -> None:
        self._ttl = ttl_seconds
        self._store: dict[str, _CacheEntry] = {}

    def get(self, key: str) -> Optional[str]:
        entry = self._store.get(key)
        now = time.time()
        if entry and entry.expires_at > now:
            return entry.value
        if entry:
            # Expired
            self._store.pop(key, None)
        return None

    def set(self, key: str, value: Optional[str]) -> None:
        self._store[key] = _CacheEntry(value=value, expires_at=time.time() + self._ttl)

    def invalidate(self, key: Optional[str] = None) -> None:
        if key is None:
            self._store.clear()
        else:
            self._store.pop(key, None)


_cache = GlobalSecretCache(ttl_seconds=60)


def validate_env_key(key: str) -> None:
    if not ENV_KEY_PATTERN.match(key):
        raise ValueError(
            "Invalid key format. Use uppercase letters, digits, and underscores, starting with a letter or underscore."
        )


def list_for_admin(session: Session) -> list[dict]:
    items = list_global_secrets(session)
    # Never expose decrypted values
    return [
        {
            "key": item.key,
            "updated_at": item.updated_at,
            "created_at": item.created_at,
            "is_set": True,
        }
        for item in items
    ]


def upsert_for_admin(session: Session, key: str, secret: str) -> None:
    validate_env_key(key)
    upsert_global_secret(session, key=key, secret=secret)
    _cache.invalidate(key)


def delete_for_admin(session: Session, key: str) -> None:
    delete_global_secret(session, key=key)
    _cache.invalidate(key)


def resolve_from_db(session: Session, key: str) -> Optional[str]:
    # Cache first
    cached = _cache.get(key)
    if cached is not None:
        return cached

    item = get_global_secret(session, key=key)
    if not item:
        _cache.set(key, None)
        return None
    try:
        value = item.get_secret()
    except Exception:
        LOGGER.exception("Failed to decrypt global secret for key %s", key)
        raise
    _cache.set(key, value)
    return value
