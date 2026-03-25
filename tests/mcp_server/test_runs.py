"""Runs tools coverage tests."""

from unittest.mock import AsyncMock

import pytest

from mcp_server.tools import runs
from tests.mcp_server.conftest import FAKE_PROJECT_ID, FAKE_RUNNER_ID


class TestRunsSpecs:
    def test_get_run_is_auth_scoped(self):
        spec = next(s for s in runs.PROXY_SPECS if s.name == "get_run")
        assert spec.scope == "auth"

    def test_get_run_result_is_auth_scoped(self):
        spec = next(s for s in runs.PROXY_SPECS if s.name == "get_run_result")
        assert spec.scope == "auth"


@pytest.mark.asyncio
async def test_list_runs_caps_page_size(fake_mcp, monkeypatch):
    get_mock = AsyncMock(return_value={"runs": []})
    monkeypatch.setattr(runs, "_get_auth", lambda: ("jwt", "uid-1"))
    monkeypatch.setattr(runs, "api", type("API", (), {"get": get_mock})())

    runs.register(fake_mcp)
    await fake_mcp.tools["list_runs"](project_id=FAKE_PROJECT_ID, page_size=999)

    assert get_mock.call_args.kwargs["page_size"] == 100


@pytest.mark.asyncio
async def test_list_runs_rejects_zero_page(fake_mcp, monkeypatch):
    monkeypatch.setattr(runs, "_get_auth", lambda: ("jwt", "uid-1"))
    runs.register(fake_mcp)

    with pytest.raises(ValueError, match="Page must be greater"):
        await fake_mcp.tools["list_runs"](project_id=FAKE_PROJECT_ID, page=0)


@pytest.mark.asyncio
async def test_run_rejects_zero_timeout(fake_mcp, monkeypatch):
    monkeypatch.setattr(runs, "_get_auth", lambda: ("jwt", "uid-1"))
    runs.register(fake_mcp)

    with pytest.raises(ValueError, match="timeout must be a positive"):
        await fake_mcp.tools["run"](
            project_id=FAKE_PROJECT_ID,
            graph_runner_id=FAKE_RUNNER_ID,
            payload={"messages": [{"role": "user", "content": "hi"}]},
            timeout=0,
        )


@pytest.mark.asyncio
async def test_run_rejects_payload_without_messages(fake_mcp, monkeypatch):
    monkeypatch.setattr(runs, "_get_auth", lambda: ("jwt", "uid-1"))
    runs.register(fake_mcp)

    with pytest.raises(ValueError, match="payload must contain a 'messages' key"):
        await fake_mcp.tools["run"](
            project_id=FAKE_PROJECT_ID,
            graph_runner_id=FAKE_RUNNER_ID,
            payload={"name": "Ada"},
        )
