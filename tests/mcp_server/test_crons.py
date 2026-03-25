from unittest.mock import AsyncMock

import pytest

from mcp_server.tools import _factory, crons
from tests.mcp_server.conftest import FAKE_CRON_ID


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

    await mcp.tools["get_cron"](FAKE_CRON_ID)
    await mcp.tools["pause_cron"](FAKE_CRON_ID)

    get_mock.assert_awaited_once_with(f"/organizations/org-123/crons/{FAKE_CRON_ID}", "jwt-token", trim=True)
    post_mock.assert_awaited_once_with(f"/organizations/org-123/crons/{FAKE_CRON_ID}/pause", "jwt-token", trim=True)
