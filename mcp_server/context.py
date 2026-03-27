"""Session-scoped organization context management.

Stores the user's selected organization in Redis, keyed by user_id and the
current MCP session when available.  Falls back to in-memory storage when
Redis is unreachable (common in local/Cursor MCP setups where Docker may not
be running).  All org-scoped tools read from here to determine which org to
operate on.
"""

import json
import logging
import time
from typing import Any

import redis.asyncio as redis
from fastmcp.server.dependencies import get_http_request, get_task_context
from redis.exceptions import AuthenticationError as RedisAuthenticationError
from redis.exceptions import ConnectionError as RedisConnectionError

from mcp_server.settings import settings

logger = logging.getLogger(__name__)

_redis: redis.Redis | None = None
_memory_store: dict[str, str] = {}
_using_memory: bool = False
_memory_fallback_since: float = 0.0
_REDIS_RETRY_INTERVAL = 60  # seconds


def _get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


def _current_session_id() -> str:
    task_context = get_task_context()
    if task_context and task_context.session_id:
        return task_context.session_id

    try:
        request = get_http_request()
    except RuntimeError:
        return "default"

    session_id = request.headers.get("mcp-session-id", "").strip()
    return session_id or "default"


def _session_key(user_id: str, session_id: str) -> str:
    return f"mcp:org_session:{user_id}:{session_id}"


def _switch_to_memory() -> None:
    global _using_memory, _memory_fallback_since
    if not _using_memory:
        logger.warning("Redis unavailable — using in-memory session store (data lost on restart)")
    _using_memory = True
    _memory_fallback_since = time.monotonic()


def _should_retry_redis() -> bool:
    if not _using_memory:
        return False
    return (time.monotonic() - _memory_fallback_since) >= _REDIS_RETRY_INTERVAL


def _recover_redis() -> None:
    global _using_memory
    logger.info("Redis recovered — switching back from memory fallback")
    _using_memory = False


async def get_active_org(user_id: str) -> dict[str, Any] | None:
    session_id = _current_session_id()
    key = _session_key(user_id, session_id)

    if not _using_memory or _should_retry_redis():
        r = _get_redis()
        try:
            raw = await r.get(key)
            if _using_memory:
                _recover_redis()
        except (RedisAuthenticationError, RedisConnectionError) as exc:
            logger.error("Redis connection/auth failed, falling back to memory: %s", exc)
            _switch_to_memory()
            raw = _memory_store.get(key)
        except OSError as exc:
            logger.error("Redis OS-level error, falling back to memory: %s", exc)
            _switch_to_memory()
            raw = _memory_store.get(key)
    else:
        raw = _memory_store.get(key)

    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning(
            "Invalid MCP org session payload for user_id=%s session_id=%s: %s (raw=%r)",
            user_id,
            session_id,
            exc,
            raw,
        )
        return None


async def set_active_org(user_id: str, org_id: str, org_name: str, role: str, release_stage: str = "public") -> None:
    session_id = _current_session_id()
    key = _session_key(user_id, session_id)
    data = json.dumps({
        "org_id": org_id,
        "org_name": org_name,
        "role": role,
        "release_stage": release_stage,
    })

    if not _using_memory or _should_retry_redis():
        r = _get_redis()
        try:
            await r.set(key, data, ex=settings.MCP_ORG_SESSION_TTL)
            if _using_memory:
                _recover_redis()
            return
        except (RedisAuthenticationError, RedisConnectionError) as exc:
            logger.error("Redis connection/auth failed, falling back to memory: %s", exc)
            _switch_to_memory()
        except OSError as exc:
            logger.error("Redis OS-level error, falling back to memory: %s", exc)
            _switch_to_memory()

    _memory_store[key] = data


async def require_org_context(user_id: str) -> dict[str, Any]:
    """Return active org or raise with a helpful message."""
    org = await get_active_org(user_id)
    if not org:
        raise ValueError(
            "No organization selected. "
            "These steps MUST be sequential (not parallel): "
            "1) list_my_organizations — see your orgs and roles, "
            "2) select_organization(organization_id) — set the active org "
            "(wait for success before calling other tools), "
            "3) get_current_context() — verify session state. "
            "Parallel calls with select_organization will race and fail."
        )
    return org


async def require_role(user_id: str, *allowed_roles: str) -> dict[str, Any]:
    """Return active org if the user's role is in allowed_roles, else raise."""
    org = await require_org_context(user_id)
    if org["role"] not in allowed_roles:
        raise ValueError(f"This operation requires one of {allowed_roles} role, but your role is '{org['role']}'.")
    return org
