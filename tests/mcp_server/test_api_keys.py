from unittest.mock import AsyncMock

import pytest

from mcp_server.tools import _factory, api_keys
from tests.mcp_server.conftest import FAKE_KEY_ID, FAKE_PROJECT_ID


@pytest.mark.asyncio
async def test_revoke_org_api_key_sends_delete_body(monkeypatch, fake_mcp):
    mcp = fake_mcp
    delete_mock = AsyncMock(return_value={"status": "ok"})
    require_org_context_mock = AsyncMock(return_value={"org_id": "org-123"})

    monkeypatch.setattr(_factory, "_get_auth", lambda: ("jwt-token", "user-123"))
    monkeypatch.setattr(_factory, "require_org_context", require_org_context_mock)
    monkeypatch.setattr(_factory.api, "delete", delete_mock)

    api_keys.register(mcp)

    result = await mcp.tools["revoke_org_api_key"](FAKE_KEY_ID)

    assert result == {"status": "ok"}
    require_org_context_mock.assert_awaited_once_with("user-123")
    delete_mock.assert_awaited_once_with(
        "/auth/org-api-key",
        "jwt-token",
        trim=True,
        json={"key_id": FAKE_KEY_ID},
        organization_id="org-123",
    )


@pytest.mark.asyncio
async def test_create_project_api_key_sends_correct_body(monkeypatch, fake_mcp):
    mcp = fake_mcp
    post_mock = AsyncMock(return_value={"api_key": "sk-abc"})

    monkeypatch.setattr(_factory, "_get_auth", lambda: ("jwt-token", "user-123"))
    monkeypatch.setattr(_factory.api, "post", post_mock)

    api_keys.register(mcp)

    result = await mcp.tools["create_project_api_key"](FAKE_PROJECT_ID, "my-key")

    assert result == {"api_key": "sk-abc"}
    post_mock.assert_awaited_once_with(
        "/auth/api-key",
        "jwt-token",
        trim=True,
        json={"project_id": FAKE_PROJECT_ID, "key_name": "my-key"},
    )


@pytest.mark.asyncio
async def test_create_org_api_key_sends_correct_body(monkeypatch, fake_mcp):
    mcp = fake_mcp
    post_mock = AsyncMock(return_value={"api_key": "sk-org"})
    require_org_context_mock = AsyncMock(return_value={"org_id": "org-123"})

    monkeypatch.setattr(_factory, "_get_auth", lambda: ("jwt-token", "user-123"))
    monkeypatch.setattr(_factory, "require_org_context", require_org_context_mock)
    monkeypatch.setattr(_factory.api, "post", post_mock)

    api_keys.register(mcp)

    result = await mcp.tools["create_org_api_key"]("my-key")

    assert result == {"api_key": "sk-org"}
    require_org_context_mock.assert_awaited_once_with("user-123")
    post_mock.assert_awaited_once_with(
        "/auth/org-api-key",
        "jwt-token",
        trim=True,
        json={"key_name": "my-key", "org_id": "org-123"},
    )
