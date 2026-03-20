from unittest.mock import AsyncMock

import pytest

from mcp_server.tools import _factory, qa


class FakeMCP:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def decorator(func):
            self.tools[func.__name__] = func
            return func

        return decorator


@pytest.fixture
def mcp(monkeypatch):
    monkeypatch.setattr(_factory, "_get_auth", lambda: ("jwt-token", "user-1"))
    fake = FakeMCP()
    qa.register(fake)
    return fake


@pytest.mark.asyncio
async def test_update_dataset_sends_name_as_query_param(mcp, monkeypatch):
    patch_mock = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(_factory.api, "patch", patch_mock)

    await mcp.tools["update_dataset"]("proj-1", "ds-1", "New Name")

    patch_mock.assert_awaited_once_with(
        "/projects/proj-1/qa/datasets/ds-1",
        "jwt-token",
        trim=True,
        dataset_name="New Name",
    )


@pytest.mark.asyncio
async def test_run_evaluation_sends_version_output_id_in_body(mcp, monkeypatch):
    post_mock = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(_factory.api, "post", post_mock)

    await mcp.tools["run_evaluation"]("proj-1", "judge-1", "vo-123")

    post_mock.assert_awaited_once_with(
        "/projects/proj-1/qa/llm-judges/judge-1/evaluations/run",
        "jwt-token",
        trim=True,
        json={"version_output_id": "vo-123"},
    )
