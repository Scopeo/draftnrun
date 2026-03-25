from unittest.mock import AsyncMock

import pytest

from mcp_server.tools import _factory, oauth_connections
from tests.mcp_server.conftest import FAKE_CONN_ID


@pytest.mark.asyncio
async def test_list_oauth_connections_requires_role(monkeypatch, fake_mcp):
    role_mock = AsyncMock(return_value={"org_id": "org-123"})
    get_mock = AsyncMock(return_value=[{"id": "c1"}])

    monkeypatch.setattr(_factory, "_get_auth", lambda: ("jwt-token", "user-123"))
    monkeypatch.setattr(_factory, "require_role", role_mock)
    monkeypatch.setattr(_factory.api, "get", get_mock)

    oauth_connections.register(fake_mcp)

    result = await fake_mcp.tools["list_oauth_connections"]()

    assert result == [{"id": "c1"}]
    role_mock.assert_awaited_once_with("user-123", "developer", "admin", "super_admin")
    get_mock.assert_awaited_once_with("/organizations/org-123/oauth-connections", "jwt-token", trim=True)


@pytest.mark.asyncio
async def test_check_oauth_status_sends_query_params(monkeypatch, fake_mcp):
    role_mock = AsyncMock(return_value={"org_id": "org-123"})
    get_mock = AsyncMock(return_value={"status": "active"})

    monkeypatch.setattr(_factory, "_get_auth", lambda: ("jwt-token", "user-123"))
    monkeypatch.setattr(_factory, "require_role", role_mock)
    monkeypatch.setattr(_factory.api, "get", get_mock)

    oauth_connections.register(fake_mcp)

    result = await fake_mcp.tools["check_oauth_status"]("google-mail", FAKE_CONN_ID)

    assert result == {"status": "active"}
    role_mock.assert_awaited_once_with("user-123", "developer", "admin", "super_admin")
    get_mock.assert_awaited_once_with(
        "/organizations/org-123/oauth-connections/status",
        "jwt-token",
        trim=True,
        provider_config_key="google-mail",
        connection_id=FAKE_CONN_ID,
    )


@pytest.mark.asyncio
async def test_revoke_oauth_sends_provider_query_param(monkeypatch, fake_mcp):
    role_mock = AsyncMock(return_value={"org_id": "org-123"})
    delete_mock = AsyncMock(return_value={"status": "ok"})

    monkeypatch.setattr(_factory, "_get_auth", lambda: ("jwt-token", "user-123"))
    monkeypatch.setattr(_factory, "require_role", role_mock)
    monkeypatch.setattr(_factory.api, "delete", delete_mock)

    oauth_connections.register(fake_mcp)

    result = await fake_mcp.tools["revoke_oauth"](FAKE_CONN_ID, "slack")

    assert result == {"status": "ok"}
    role_mock.assert_awaited_once_with("user-123", "developer", "admin", "super_admin")
    delete_mock.assert_awaited_once_with(
        f"/organizations/org-123/oauth-connections/{FAKE_CONN_ID}",
        "jwt-token",
        trim=True,
        provider_config_key="slack",
    )
