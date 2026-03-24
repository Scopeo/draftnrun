from unittest.mock import AsyncMock

import pytest

from mcp_server.tools import _factory, qa
from tests.mcp_server.conftest import (
    FAKE_DATASET_ID,
    FAKE_JUDGE_ID,
    FAKE_PROJECT_ID,
    FAKE_VERSION_OUTPUT_ID,
)


@pytest.fixture
def mcp(fake_mcp, monkeypatch):
    monkeypatch.setattr(_factory, "_get_auth", lambda: ("jwt-token", "user-1"))
    qa.register(fake_mcp)
    return fake_mcp


@pytest.mark.asyncio
async def test_update_dataset_sends_name_as_query_param(mcp, monkeypatch):
    patch_mock = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(_factory.api, "patch", patch_mock)

    await mcp.tools["update_dataset"](FAKE_PROJECT_ID, FAKE_DATASET_ID, "New Name")

    patch_mock.assert_awaited_once_with(
        f"/projects/{FAKE_PROJECT_ID}/qa/datasets/{FAKE_DATASET_ID}",
        "jwt-token",
        trim=True,
        dataset_name="New Name",
    )


@pytest.mark.asyncio
async def test_run_evaluation_sends_version_output_id_in_body(mcp, monkeypatch):
    post_mock = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(_factory.api, "post", post_mock)

    await mcp.tools["run_evaluation"](FAKE_PROJECT_ID, FAKE_JUDGE_ID, FAKE_VERSION_OUTPUT_ID)

    post_mock.assert_awaited_once_with(
        f"/projects/{FAKE_PROJECT_ID}/qa/llm-judges/{FAKE_JUDGE_ID}/evaluations/run",
        "jwt-token",
        trim=True,
        json={"version_output_id": FAKE_VERSION_OUTPUT_ID},
    )
