from unittest.mock import AsyncMock

import pytest

from mcp_server.tools import context_tools
from tests.mcp_server.conftest import FAKE_ORG_ID


class FakeMCP:
    def __init__(self):
        self.tools = {}
        self.tool_annotations = {}

    def tool(self, annotations=None):
        def decorator(func):
            self.tools[func.__name__] = func
            self.tool_annotations[func.__name__] = annotations
            return func

        return decorator


@pytest.mark.asyncio
async def test_invite_org_member_checks_role_in_target_org(monkeypatch):
    mcp = FakeMCP()
    list_orgs_mock = AsyncMock(
        return_value=[
            {"id": "org-active", "name": "Active Org", "role": "admin"},
            {"id": FAKE_ORG_ID, "name": "Target Org", "role": "member"},
        ]
    )
    invite_mock = AsyncMock(return_value={"status": "ok"})

    monkeypatch.setattr(context_tools, "_get_auth", lambda: ("jwt-token", "user-123"))
    monkeypatch.setattr(context_tools, "list_user_organizations", list_orgs_mock)
    monkeypatch.setattr(context_tools, "invite_member", invite_mock)

    context_tools.register(mcp)

    with pytest.raises(ValueError, match="role there is 'member'"):
        await mcp.tools["invite_org_member"](FAKE_ORG_ID, "person@example.com")

    invite_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_invite_org_member_invites_when_target_org_role_is_admin(monkeypatch):
    mcp = FakeMCP()
    list_orgs_mock = AsyncMock(
        return_value=[
            {"id": FAKE_ORG_ID, "name": "Target Org", "role": "admin"},
        ]
    )
    invite_mock = AsyncMock(return_value={"status": "ok"})

    monkeypatch.setattr(context_tools, "_get_auth", lambda: ("jwt-token", "user-123"))
    monkeypatch.setattr(context_tools, "list_user_organizations", list_orgs_mock)
    monkeypatch.setattr(context_tools, "invite_member", invite_mock)

    context_tools.register(mcp)

    result = await mcp.tools["invite_org_member"](FAKE_ORG_ID, "person@example.com", "developer")

    assert result == {"status": "ok"}
    invite_mock.assert_awaited_once_with("jwt-token", FAKE_ORG_ID, "person@example.com", "developer")


@pytest.mark.asyncio
async def test_select_organization_stores_org_with_release_stage(monkeypatch):
    mcp = FakeMCP()
    list_orgs_mock = AsyncMock(return_value=[{"id": FAKE_ORG_ID, "name": "Acme", "role": "developer"}])
    stage_mock = AsyncMock(return_value="beta")
    set_org_mock = AsyncMock()

    monkeypatch.setattr(context_tools, "_get_auth", lambda: ("jwt-token", "user-123"))
    monkeypatch.setattr(context_tools, "list_user_organizations", list_orgs_mock)
    monkeypatch.setattr(context_tools, "fetch_org_release_stage", stage_mock)
    monkeypatch.setattr(context_tools, "set_active_org", set_org_mock)

    context_tools.register(mcp)

    result = await mcp.tools["select_organization"](FAKE_ORG_ID)

    assert result == {
        "status": "ok",
        "org_id": FAKE_ORG_ID,
        "org_name": "Acme",
        "role": "developer",
        "release_stage": "beta",
    }
    set_org_mock.assert_awaited_once_with("user-123", FAKE_ORG_ID, "Acme", "developer", "beta")


@pytest.mark.asyncio
async def test_select_organization_rejects_unknown_org(monkeypatch):
    mcp = FakeMCP()
    list_orgs_mock = AsyncMock(return_value=[])

    monkeypatch.setattr(context_tools, "_get_auth", lambda: ("jwt-token", "user-123"))
    monkeypatch.setattr(context_tools, "list_user_organizations", list_orgs_mock)

    context_tools.register(mcp)

    with pytest.raises(ValueError, match="not found in your memberships"):
        await mcp.tools["select_organization"](FAKE_ORG_ID)


@pytest.mark.asyncio
async def test_list_my_organizations_returns_memberships(monkeypatch):
    mcp = FakeMCP()
    orgs = [{"id": FAKE_ORG_ID, "name": "Acme", "role": "admin"}]
    list_orgs_mock = AsyncMock(return_value=orgs)

    monkeypatch.setattr(context_tools, "_get_auth", lambda: ("jwt-token", "user-123"))
    monkeypatch.setattr(context_tools, "list_user_organizations", list_orgs_mock)

    context_tools.register(mcp)

    assert await mcp.tools["list_my_organizations"]() == orgs


@pytest.mark.asyncio
async def test_get_current_context_reports_session_state(monkeypatch):
    mcp = FakeMCP()

    class FakeToken:
        token = "jwt-token"
        claims = {"sub": "user-123", "email": "dev@test.com"}

    get_org_mock = AsyncMock(return_value={"org_id": FAKE_ORG_ID, "role": "member"})

    monkeypatch.setattr(context_tools, "get_access_token", lambda: FakeToken())
    monkeypatch.setattr(context_tools, "get_active_org", get_org_mock)
    monkeypatch.setattr(context_tools._ctx, "_current_session_id", lambda: "session-abc")
    monkeypatch.setattr(context_tools._ctx, "_using_memory", False)

    context_tools.register(mcp)

    result = await mcp.tools["get_current_context"]()

    assert result["user_id"] == "user-123"
    assert result["email"] == "dev@test.com"
    assert result["active_organization"] == {"org_id": FAKE_ORG_ID, "role": "member"}
    assert result["session"] == {"session_id": "session-abc", "storage_backend": "redis"}
