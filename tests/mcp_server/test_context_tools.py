from unittest.mock import AsyncMock

import pytest

from mcp_server.tools import context_tools


class FakeMCP:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def decorator(func):
            self.tools[func.__name__] = func
            return func

        return decorator


@pytest.mark.asyncio
async def test_invite_org_member_checks_role_in_target_org(monkeypatch):
    mcp = FakeMCP()
    list_orgs_mock = AsyncMock(
        return_value=[
            {"id": "org-active", "name": "Active Org", "role": "admin"},
            {"id": "org-target", "name": "Target Org", "role": "member"},
        ]
    )
    invite_mock = AsyncMock(return_value={"status": "ok"})

    monkeypatch.setattr(context_tools, "_get_auth", lambda: ("jwt-token", "user-123"))
    monkeypatch.setattr(context_tools, "list_user_organizations", list_orgs_mock)
    monkeypatch.setattr(context_tools, "invite_member", invite_mock)

    context_tools.register(mcp)

    with pytest.raises(ValueError, match="role there is 'member'"):
        await mcp.tools["invite_org_member"]("org-target", "person@example.com")

    invite_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_invite_org_member_invites_when_target_org_role_is_admin(monkeypatch):
    mcp = FakeMCP()
    list_orgs_mock = AsyncMock(
        return_value=[
            {"id": "org-target", "name": "Target Org", "role": "admin"},
        ]
    )
    invite_mock = AsyncMock(return_value={"status": "ok"})

    monkeypatch.setattr(context_tools, "_get_auth", lambda: ("jwt-token", "user-123"))
    monkeypatch.setattr(context_tools, "list_user_organizations", list_orgs_mock)
    monkeypatch.setattr(context_tools, "invite_member", invite_mock)

    context_tools.register(mcp)

    result = await mcp.tools["invite_org_member"]("org-target", "person@example.com", "developer")

    assert result == {"status": "ok"}
    invite_mock.assert_awaited_once_with("jwt-token", "org-target", "person@example.com", "developer")
