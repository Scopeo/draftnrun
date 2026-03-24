from unittest.mock import AsyncMock

import pytest

from mcp_server.client import ToolError
from mcp_server.tools import agent_config
from tests.mcp_server.conftest import FAKE_AGENT_ID, FAKE_RUNNER_ID

OVERVIEW_AGENT = {"project_type": "agent"}
OVERVIEW_WORKFLOW = {"project_type": "workflow"}

MODEL_OPTIONS = [
    {"value": "openai:gpt-4.1", "label": "GPT-4.1"},
    {"value": "openai:gpt-4.1-mini", "label": "GPT-4.1 Mini"},
    {"value": "openai:gpt-5", "label": "GPT-5"},
    {"value": "anthropic:claude-sonnet-4-5", "label": "Claude Sonnet 4.5"},
]


def _make_model_parameters(model_value="openai:gpt-4.1"):
    return [
        {
            "name": "completion_model",
            "value": model_value,
            "ui_component_properties": {"options": MODEL_OPTIONS},
        },
        {"name": "default_temperature", "value": 0.7},
    ]


@pytest.mark.asyncio
async def test_add_tool_to_agent_rejects_non_function_callable_component(monkeypatch, fake_mcp):
    require_org_context_mock = AsyncMock(return_value={"org_id": "org-123", "release_stage": None})
    fetch_component_mock = AsyncMock(
        return_value={
            "name": "router",
            "component_name": "router",
            "component_version_id": "component-version-1",
            "function_callable": False,
            "integration": None,
        }
    )
    agent_data = {
        "name": "Agent",
        "description": "",
        "system_prompt": "",
        "model_parameters": [],
        "tools": [],
    }
    get_mock = AsyncMock(side_effect=[OVERVIEW_AGENT, agent_data])
    put_mock = AsyncMock()

    monkeypatch.setattr(agent_config, "_get_auth", lambda: ("jwt-token", "user-123"))
    monkeypatch.setattr(agent_config, "require_org_context", require_org_context_mock)
    monkeypatch.setattr(agent_config, "_fetch_component_by_name", fetch_component_mock)
    monkeypatch.setattr(agent_config.api, "get", get_mock)
    monkeypatch.setattr(agent_config.api, "put", put_mock)

    agent_config.register(fake_mcp)

    with pytest.raises(ValueError, match="not function_callable"):
        await fake_mcp.tools["add_tool_to_agent"](FAKE_AGENT_ID, FAKE_RUNNER_ID, "router")

    put_mock.assert_not_awaited()
    fetch_component_mock.assert_awaited_once_with("jwt-token", "org-123", "public", "router")


@pytest.mark.asyncio
async def test_add_tool_to_agent_rejects_integration_backed_component(monkeypatch, fake_mcp):
    require_org_context_mock = AsyncMock(return_value={"org_id": "org-123", "release_stage": None})
    fetch_component_mock = AsyncMock(
        return_value={
            "name": "Gmail Sender",
            "component_name": "Gmail Sender",
            "component_version_id": "component-version-2",
            "function_callable": True,
            "integration": {"name": "gmail", "service": "google"},
        }
    )
    agent_data = {
        "name": "Agent",
        "description": "",
        "system_prompt": "",
        "model_parameters": [],
        "tools": [],
    }
    get_mock = AsyncMock(side_effect=[OVERVIEW_AGENT, agent_data])
    put_mock = AsyncMock()

    monkeypatch.setattr(agent_config, "_get_auth", lambda: ("jwt-token", "user-123"))
    monkeypatch.setattr(agent_config, "require_org_context", require_org_context_mock)
    monkeypatch.setattr(agent_config, "_fetch_component_by_name", fetch_component_mock)
    monkeypatch.setattr(agent_config.api, "get", get_mock)
    monkeypatch.setattr(agent_config.api, "put", put_mock)

    agent_config.register(fake_mcp)

    with pytest.raises(ValueError, match="cannot create the required integration relationship"):
        await fake_mcp.tools["add_tool_to_agent"](FAKE_AGENT_ID, FAKE_RUNNER_ID, "Gmail Sender")

    put_mock.assert_not_awaited()
    fetch_component_mock.assert_awaited_once_with("jwt-token", "org-123", "public", "Gmail Sender")


@pytest.mark.asyncio
async def test_configure_agent_reports_ignored_missing_model_parameters(monkeypatch, fake_mcp):
    agent_data = {
        "name": "Agent",
        "description": "",
        "system_prompt": "Existing system prompt",
        "model_parameters": _make_model_parameters(),
        "tools": [],
    }
    get_mock = AsyncMock(side_effect=[OVERVIEW_AGENT, agent_data])
    put_mock = AsyncMock()

    monkeypatch.setattr(agent_config, "_get_auth", lambda: ("jwt-token", "user-123"))
    monkeypatch.setattr(agent_config.api, "get", get_mock)
    monkeypatch.setattr(agent_config.api, "put", put_mock)

    agent_config.register(fake_mcp)

    result = await fake_mcp.tools["configure_agent"](
        FAKE_AGENT_ID,
        FAKE_RUNNER_ID,
        model="gpt-4.1",
        max_tokens=2048,
    )

    assert result["status"] == "ok"
    assert any("Ignored 'max_tokens'" in warning for warning in result["warnings"])
    put_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_configure_agent_rejects_invalid_model(monkeypatch, fake_mcp):
    agent_data = {
        "name": "Agent",
        "description": "",
        "system_prompt": "",
        "model_parameters": _make_model_parameters(),
        "tools": [],
    }
    get_mock = AsyncMock(side_effect=[OVERVIEW_AGENT, agent_data])
    put_mock = AsyncMock()

    monkeypatch.setattr(agent_config, "_get_auth", lambda: ("jwt-token", "user-123"))
    monkeypatch.setattr(agent_config.api, "get", get_mock)
    monkeypatch.setattr(agent_config.api, "put", put_mock)

    agent_config.register(fake_mcp)

    with pytest.raises(ValueError, match="not available"):
        await fake_mcp.tools["configure_agent"](
            FAKE_AGENT_ID, FAKE_RUNNER_ID, model="gpt-4o",
        )

    put_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_configure_agent_accepts_valid_model(monkeypatch, fake_mcp):
    agent_data = {
        "name": "Agent",
        "description": "",
        "system_prompt": "",
        "model_parameters": _make_model_parameters(),
        "tools": [],
    }
    get_mock = AsyncMock(side_effect=[OVERVIEW_AGENT, agent_data])
    put_mock = AsyncMock()

    monkeypatch.setattr(agent_config, "_get_auth", lambda: ("jwt-token", "user-123"))
    monkeypatch.setattr(agent_config.api, "get", get_mock)
    monkeypatch.setattr(agent_config.api, "put", put_mock)

    agent_config.register(fake_mcp)

    result = await fake_mcp.tools["configure_agent"](
        FAKE_AGENT_ID, FAKE_RUNNER_ID, model="anthropic:claude-sonnet-4-5",
    )

    assert result["status"] == "ok"
    put_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_configure_agent_skips_model_validation_when_no_options(monkeypatch, fake_mcp):
    """When the completion_model param has no options list, any model is accepted."""
    agent_data = {
        "name": "Agent",
        "description": "",
        "system_prompt": "",
        "model_parameters": [
            {"name": "completion_model", "value": "openai:gpt-4.1"},
        ],
        "tools": [],
    }
    get_mock = AsyncMock(side_effect=[OVERVIEW_AGENT, agent_data])
    put_mock = AsyncMock()

    monkeypatch.setattr(agent_config, "_get_auth", lambda: ("jwt-token", "user-123"))
    monkeypatch.setattr(agent_config.api, "get", get_mock)
    monkeypatch.setattr(agent_config.api, "put", put_mock)

    agent_config.register(fake_mcp)

    result = await fake_mcp.tools["configure_agent"](
        FAKE_AGENT_ID, FAKE_RUNNER_ID, model="anything:works-here",
    )

    assert result["status"] == "ok"
    put_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_configure_agent_rejects_workflow_project(monkeypatch, fake_mcp):
    get_mock = AsyncMock(return_value=OVERVIEW_WORKFLOW)
    monkeypatch.setattr(agent_config, "_get_auth", lambda: ("jwt-token", "user-123"))
    monkeypatch.setattr(agent_config.api, "get", get_mock)
    agent_config.register(fake_mcp)

    with pytest.raises(ToolError, match="AGENT projects"):
        await fake_mcp.tools["configure_agent"](FAKE_AGENT_ID, FAKE_RUNNER_ID, system_prompt="test")
