"""Runs tools coverage tests."""

from unittest.mock import AsyncMock, patch

import pytest

from mcp_server.tools import runs
from tests.mcp_server.conftest import FAKE_PROJECT_ID, FAKE_RUN_ID, FAKE_RUNNER_ID

FAKE_ORG = {"org_id": "org-1", "org_name": "Test Org"}


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
    with patch("mcp_server.tools.runs.require_org_context", new_callable=AsyncMock, return_value=FAKE_ORG):
        await fake_mcp.tools["list_runs"](project_id=FAKE_PROJECT_ID, page_size=999)

    assert get_mock.call_args.kwargs["page_size"] == 100


@pytest.mark.asyncio
async def test_list_runs_rejects_zero_page(fake_mcp, monkeypatch):
    monkeypatch.setattr(runs, "_get_auth", lambda: ("jwt", "uid-1"))
    runs.register(fake_mcp)

    with pytest.raises(ValueError, match="Page must be >= 1"):
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


@pytest.mark.asyncio
async def test_retry_run_rejects_missing_target(fake_mcp, monkeypatch):
    monkeypatch.setattr(runs, "_get_auth", lambda: ("jwt", "uid-1"))
    runs.register(fake_mcp)

    with pytest.raises(ValueError, match="Either env or graph_runner_id must be provided"):
        await fake_mcp.tools["retry_run"](project_id=FAKE_PROJECT_ID, run_id=FAKE_RUN_ID)


@pytest.mark.asyncio
async def test_retry_run_posts_body(fake_mcp, monkeypatch):
    post_mock = AsyncMock(return_value={"run_id": "new-run", "status": "pending"})
    monkeypatch.setattr(runs, "_get_auth", lambda: ("jwt", "uid-1"))
    monkeypatch.setattr(runs, "api", type("API", (), {"post": post_mock})())
    runs.register(fake_mcp)

    await fake_mcp.tools["retry_run"](
        project_id=FAKE_PROJECT_ID,
        run_id=FAKE_RUN_ID,
        env="draft",
    )

    assert post_mock.call_args.args[0] == f"/projects/{FAKE_PROJECT_ID}/runs/{FAKE_RUN_ID}/retry"
    assert post_mock.call_args.kwargs["json"] == {"env": "draft"}
