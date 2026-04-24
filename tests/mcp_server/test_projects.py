from unittest.mock import AsyncMock

import pytest

from mcp_server.tools import projects
from tests.mcp_server.conftest import FAKE_PROJECT_ID


@pytest.mark.asyncio
async def test_get_project_overview_returns_versioning_safety_metadata(fake_mcp, monkeypatch):
    mcp = fake_mcp
    get_mock = AsyncMock(
        side_effect=[
            {
                "id": FAKE_PROJECT_ID,
                "name": "Demo Agent",
                "description": "desc",
                "type": "AGENT",
                "graph_runners": [
                    {"graph_runner_id": "draft-456", "env": "draft", "tag_name": None},
                    {"graph_runner_id": "prod-789", "env": "production", "tag_name": "v1"},
                ],
            },
            {"runs": [{"id": "run-1"}]},
        ]
    )

    monkeypatch.setattr(projects, "_get_auth", lambda: ("jwt-token", "user-123"))
    monkeypatch.setattr(projects.api, "get", get_mock)

    projects.register(mcp)

    result = await mcp.tools["get_project_overview"](FAKE_PROJECT_ID)

    assert result["editable_draft_graph_runner_id"] == "draft-456"
    assert result["production_graph_runner_id"] == "prod-789"
    assert result["has_production_deployment"] is True
    assert result["production_only_capabilities"] == {
        "cron_jobs": True,
        "widgets": True,
        "event_triggers": True,
    }
    assert any("true draft runner" in warning for warning in result["warnings"])
    assert any(f"save_graph_version('{FAKE_PROJECT_ID}', 'draft-456')" in step for step in result["safe_next_steps"])
    assert any("prod-789" in step for step in result["safe_next_steps"])


@pytest.mark.asyncio
async def test_get_project_overview_fallback_field_names(fake_mcp, monkeypatch):
    """Backend may return project_id/project_name/project_type instead of id/name/type."""
    mcp = fake_mcp
    get_mock = AsyncMock(
        side_effect=[
            {
                "project_id": FAKE_PROJECT_ID,
                "project_name": "Prefixed Project",
                "description": "desc",
                "project_type": "WORKFLOW",
                "graph_runners": [
                    {"graph_runner_id": "draft-789", "env": "draft", "tag_name": None},
                ],
            },
            {"runs": []},
        ]
    )

    monkeypatch.setattr(projects, "_get_auth", lambda: ("jwt-token", "user-123"))
    monkeypatch.setattr(projects.api, "get", get_mock)

    projects.register(mcp)

    result = await mcp.tools["get_project_overview"](FAKE_PROJECT_ID)

    assert result["project"]["id"] == FAKE_PROJECT_ID
    assert result["project"]["name"] == "Prefixed Project"
    assert result["project"]["type"] == "WORKFLOW"


@pytest.mark.asyncio
async def test_create_workflow_rejects_blank_name(fake_mcp):
    mcp = fake_mcp

    projects.register(mcp)

    with pytest.raises(ValueError, match="name must not be empty"):
        await mcp.tools["create_workflow"]("   ")


@pytest.mark.asyncio
async def test_create_workflow_strips_name_before_sending(fake_mcp, monkeypatch):
    mcp = fake_mcp
    post_mock = AsyncMock(return_value={"id": FAKE_PROJECT_ID})
    require_role_mock = AsyncMock(return_value={"org_id": "org-123"})

    monkeypatch.setattr(projects, "_get_auth", lambda: ("jwt-token", "user-123"))
    monkeypatch.setattr(projects, "require_role", require_role_mock)
    monkeypatch.setattr(
        projects,
        "generate_entity_defaults",
        lambda: {"id": FAKE_PROJECT_ID, "icon": "workflow", "icon_color": "blue"},
    )
    monkeypatch.setattr(projects.api, "post", post_mock)

    projects.register(mcp)

    await mcp.tools["create_workflow"]("  Demo Project  ")

    assert post_mock.await_args.kwargs["json"]["project_name"] == "Demo Project"


@pytest.mark.asyncio
async def test_update_project_rejects_empty_body(fake_mcp, monkeypatch):
    mcp = fake_mcp
    patch_mock = AsyncMock()

    monkeypatch.setattr(projects, "_get_auth", lambda: ("jwt-token", "user-123"))
    monkeypatch.setattr(projects.api, "patch", patch_mock)

    projects.register(mcp)

    with pytest.raises(ValueError, match="At least one field .* must be provided to update"):
        await mcp.tools["update_project"](FAKE_PROJECT_ID)

    patch_mock.assert_not_awaited()
