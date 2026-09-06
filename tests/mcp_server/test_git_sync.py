from unittest.mock import AsyncMock

import pytest

from mcp_server.tools import _factory, git_sync
from mcp_server.tools._roles import DEVELOPER_ROLES
from tests.mcp_server.conftest import FAKE_ORG_ID


def _spec(name: str):
    return next(s for s in git_sync.SPECS if s.name == name)


def test_write_tools_require_developer_role():
    for name in ("configure_git_sync", "disconnect_git_sync"):
        spec = _spec(name)
        assert spec.scope == "role"
        assert spec.roles == DEVELOPER_ROLES


def test_read_tools_are_org_scoped():
    for name in ("list_git_sync_configs", "get_git_sync_config"):
        assert _spec(name).scope == "org"


@pytest.mark.asyncio
async def test_configure_git_sync_sends_body_with_defaults(monkeypatch, fake_mcp):
    post_mock = AsyncMock(return_value={"status": "ok"})
    role_mock = AsyncMock(return_value={"org_id": FAKE_ORG_ID})

    monkeypatch.setattr(_factory, "_get_auth", lambda: ("jwt-token", "user-123"))
    monkeypatch.setattr(_factory, "require_role", role_mock)
    monkeypatch.setattr(_factory.api, "post", post_mock)

    git_sync.register(fake_mcp)

    await fake_mcp.tools["configure_git_sync"]("acme", "agents-repo", github_installation_id=42)

    role_mock.assert_awaited_once_with("user-123", *DEVELOPER_ROLES)
    post_mock.assert_awaited_once_with(
        f"/organizations/{FAKE_ORG_ID}/git-sync",
        "jwt-token",
        trim=True,
        json={
            "github_owner": "acme",
            "github_repo_name": "agents-repo",
            "branch": "main",
            "github_installation_id": 42,
            "project_type": "workflow",
        },
    )
