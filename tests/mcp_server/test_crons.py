from unittest.mock import AsyncMock, call

import pytest

from mcp_server.tools import _factory, crons


class FakeMCP:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def decorator(func):
            self.tools[func.__name__] = func
            return func

        return decorator


@pytest.mark.asyncio
async def test_cron_tools_interpolate_cron_ids(monkeypatch):
    mcp = FakeMCP()
    require_org_context_mock = AsyncMock(return_value={"org_id": "org-123"})
    get_mock = AsyncMock(return_value={"id": "cron"})
    post_mock = AsyncMock(return_value={"status": "ok"})

    require_role_mock = AsyncMock(return_value={"org_id": "org-123"})

    monkeypatch.setattr(_factory, "_get_auth", lambda: ("jwt-token", "user-123"))
    monkeypatch.setattr(_factory, "require_org_context", require_org_context_mock)
    monkeypatch.setattr(_factory, "require_role", require_role_mock)
    monkeypatch.setattr(_factory.api, "get", get_mock)
    monkeypatch.setattr(_factory.api, "post", post_mock)

    crons.register(mcp)

    await mcp.tools["get_cron"]("cron/with spaces?#")
    await mcp.tools["pause_cron"]("cron/with spaces?#")
    await mcp.tools["trigger_cron"]("cron/with spaces?#")

    encoded = "cron%2Fwith%20spaces%3F%23"
    get_mock.assert_awaited_once_with(f"/organizations/org-123/crons/{encoded}", "jwt-token", trim=True)
    post_mock.assert_has_awaits(
        [
            call(f"/organizations/org-123/crons/{encoded}/pause", "jwt-token", trim=True),
            call(f"/organizations/org-123/crons/{encoded}/trigger", "jwt-token", trim=True),
        ]
    )
