from unittest.mock import AsyncMock

import pytest

from mcp_server.tools import knowledge
from tests.mcp_server.conftest import FAKE_DOC_ID, FAKE_SOURCE_ID


@pytest.mark.asyncio
async def test_update_document_chunks_requires_explicit_full_replacement_acknowledgement(fake_mcp):
    knowledge.register(fake_mcp)

    with pytest.raises(ValueError, match="blocked by default"):
        await fake_mcp.tools["update_document_chunks"](
            FAKE_SOURCE_ID,
            FAKE_DOC_ID,
            [{"content": "replacement"}],
        )


@pytest.mark.asyncio
async def test_update_document_chunks_calls_backend_when_explicitly_confirmed(monkeypatch, fake_mcp):
    require_role_mock = AsyncMock(return_value={"org_id": "org-123"})
    put_mock = AsyncMock(return_value={"status": "ok"})

    monkeypatch.setattr(knowledge, "_get_auth", lambda: ("jwt-token", "user-123"))
    monkeypatch.setattr(knowledge, "require_role", require_role_mock)
    monkeypatch.setattr(knowledge.api, "put", put_mock)

    knowledge.register(fake_mcp)

    result = await fake_mcp.tools["update_document_chunks"](
        FAKE_SOURCE_ID,
        FAKE_DOC_ID,
        [{"content": "replacement"}],
        confirm_full_replacement=True,
    )

    assert result == {"status": "ok"}
    require_role_mock.assert_awaited_once_with("user-123", "developer", "admin", "super_admin")
    put_mock.assert_awaited_once_with(
        f"/knowledge/organizations/org-123/sources/{FAKE_SOURCE_ID}/documents/{FAKE_DOC_ID}",
        "jwt-token",
        json=[{"content": "replacement"}],
    )


@pytest.mark.asyncio
async def test_update_document_chunks_requires_developer_role(monkeypatch, fake_mcp):
    require_role_mock = AsyncMock(side_effect=ValueError("Role 'member' is not allowed"))

    monkeypatch.setattr(knowledge, "_get_auth", lambda: ("jwt-token", "user-123"))
    monkeypatch.setattr(knowledge, "require_role", require_role_mock)

    knowledge.register(fake_mcp)

    with pytest.raises(ValueError, match="not allowed"):
        await fake_mcp.tools["update_document_chunks"](
            FAKE_SOURCE_ID,
            FAKE_DOC_ID,
            [{"content": "replacement"}],
            confirm_full_replacement=True,
        )

    require_role_mock.assert_awaited_once_with("user-123", "developer", "admin", "super_admin")
