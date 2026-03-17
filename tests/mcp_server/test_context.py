import json

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from mcp_server import context


@pytest.fixture(autouse=True)
def _reset_memory_fallback():
    """Ensure each test starts with Redis as primary (no memory fallback)."""
    context._using_memory = False
    context._memory_fallback_since = 0.0
    context._memory_store.clear()
    yield
    context._using_memory = False
    context._memory_fallback_since = 0.0
    context._memory_store.clear()


class FakeRequest:
    def __init__(self, session_id: str):
        self.headers = {"mcp-session-id": session_id}


class FakeRedis:
    def __init__(self, value: str | None):
        self.value = value
        self.last_key = None

    async def get(self, key: str):
        self.last_key = key
        return self.value


class FakeRedisWriter:
    def __init__(self):
        self.last_call = None

    async def set(self, key: str, value: str, ex: int):
        self.last_call = (key, value, ex)


class FakeRedisBroken:
    async def get(self, key: str):
        raise RedisConnectionError("Connection refused")

    async def set(self, key: str, value: str, ex: int):
        raise RedisConnectionError("Connection refused")


@pytest.mark.asyncio
async def test_get_active_org_uses_mcp_session_header(monkeypatch):
    redis_client = FakeRedis(json.dumps({"org_id": "org-123"}))

    monkeypatch.setattr(context, "_get_redis", lambda: redis_client)
    monkeypatch.setattr(context, "get_task_context", lambda: None)
    monkeypatch.setattr(context, "get_http_request", lambda: FakeRequest("session-abc"))

    result = await context.get_active_org("user-123")

    assert result == {"org_id": "org-123"}
    assert redis_client.last_key == "mcp:org_session:user-123:session-abc"


@pytest.mark.asyncio
async def test_set_active_org_uses_mcp_session_header(monkeypatch):
    redis_client = FakeRedisWriter()

    monkeypatch.setattr(context, "_get_redis", lambda: redis_client)
    monkeypatch.setattr(context, "get_task_context", lambda: None)
    monkeypatch.setattr(context, "get_http_request", lambda: FakeRequest("session-xyz"))

    await context.set_active_org("user-123", "org-123", "Demo Org", "admin", "public")

    key, value, ttl = redis_client.last_call
    assert key == "mcp:org_session:user-123:session-xyz"
    assert json.loads(value) == {
        "org_id": "org-123",
        "org_name": "Demo Org",
        "role": "admin",
        "release_stage": "public",
    }
    assert ttl == context.settings.MCP_ORG_SESSION_TTL


@pytest.mark.asyncio
async def test_get_active_org_returns_none_for_invalid_json(monkeypatch, caplog):
    redis_client = FakeRedis("{not-json")

    monkeypatch.setattr(context, "_get_redis", lambda: redis_client)
    monkeypatch.setattr(context, "get_task_context", lambda: None)
    monkeypatch.setattr(context, "get_http_request", lambda: FakeRequest("session-abc"))

    with caplog.at_level("WARNING"):
        result = await context.get_active_org("user-123")

    assert result is None
    assert "Invalid MCP org session payload" in caplog.text


@pytest.mark.asyncio
async def test_falls_back_to_memory_when_redis_down(monkeypatch):
    monkeypatch.setattr(context, "_get_redis", lambda: FakeRedisBroken())
    monkeypatch.setattr(context, "get_task_context", lambda: None)
    monkeypatch.setattr(context, "get_http_request", lambda: FakeRequest("session-mem"))

    assert not context._using_memory

    await context.set_active_org("user-1", "org-1", "Test Org", "admin", "public")
    assert context._using_memory

    result = await context.get_active_org("user-1")
    assert result == {
        "org_id": "org-1",
        "org_name": "Test Org",
        "role": "admin",
        "release_stage": "public",
    }


@pytest.mark.asyncio
async def test_redis_recovery_after_retry_interval(monkeypatch):
    """When Redis recovers after the retry interval, switch back from memory."""
    broken_redis = FakeRedisBroken()

    monkeypatch.setattr(context, "_get_redis", lambda: broken_redis)
    monkeypatch.setattr(context, "get_task_context", lambda: None)
    monkeypatch.setattr(context, "get_http_request", lambda: FakeRequest("session-recover"))

    await context.set_active_org("user-1", "org-1", "Test Org", "admin", "public")
    assert context._using_memory

    context._memory_fallback_since = context.time.monotonic() - context._REDIS_RETRY_INTERVAL - 1

    good_redis = FakeRedisWriter()
    monkeypatch.setattr(context, "_get_redis", lambda: good_redis)

    await context.set_active_org("user-1", "org-1", "Test Org", "admin", "public")
    assert not context._using_memory
