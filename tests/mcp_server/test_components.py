from unittest.mock import AsyncMock

import pytest

from mcp_server.tools import components


@pytest.mark.asyncio
async def test_list_components_defaults_null_release_stage_to_public(monkeypatch, fake_mcp):
    mcp = fake_mcp
    get_mock = AsyncMock(return_value={"components": []})
    require_org_context_mock = AsyncMock(return_value={"org_id": "org-123", "release_stage": None})

    monkeypatch.setattr(components, "_get_auth", lambda: ("jwt-token", "user-123"))
    monkeypatch.setattr(components, "require_org_context", require_org_context_mock)
    monkeypatch.setattr(components.api, "get", get_mock)

    components.register(mcp)

    await mcp.tools["list_components"]()

    get_mock.assert_awaited_once_with("/components/org-123", "jwt-token", trim=False, release_stage="public")


@pytest.mark.asyncio
async def test_search_components_rejects_blank_query(fake_mcp):
    mcp = fake_mcp

    components.register(mcp)

    with pytest.raises(ValueError, match="query must not be empty"):
        await mcp.tools["search_components"]("   ")


@pytest.mark.asyncio
async def test_search_components_defaults_null_release_stage_to_public(monkeypatch, fake_mcp):
    mcp = fake_mcp
    get_mock = AsyncMock(
        return_value={"components": [{"name": "Web Search", "description": "Finds pages", "category": "Search"}]}
    )
    require_org_context_mock = AsyncMock(return_value={"org_id": "org-123", "release_stage": None})

    monkeypatch.setattr(components, "_get_auth", lambda: ("jwt-token", "user-123"))
    monkeypatch.setattr(components, "require_org_context", require_org_context_mock)
    monkeypatch.setattr(components.api, "get", get_mock)

    components.register(mcp)

    result = await mcp.tools["search_components"]("web")

    assert len(result) == 1
    get_mock.assert_awaited_once_with(
        "/components/org-123", "jwt-token", trim=False, release_stage="public",
    )
