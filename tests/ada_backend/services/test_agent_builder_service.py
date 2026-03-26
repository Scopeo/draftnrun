"""Regression tests for OAuth tool skipping via AIAgent._build_tool_cache."""

from unittest.mock import MagicMock

from engine.components.ai_agent import AIAgent
from engine.components.types import ComponentAttributes, ToolDescription


def _make_tool_description(name: str = "test_tool") -> ToolDescription:
    return ToolDescription(name=name, description="", tool_properties={}, required_tool_properties=[])


def _make_ai_agent(agent_tools: list, skip_tools_with_missing_oauth: bool = True) -> AIAgent:
    completion_service = MagicMock()
    trace_manager = MagicMock()
    trace_manager.start_span.return_value.__enter__ = MagicMock(return_value=MagicMock())
    trace_manager.start_span.return_value.__exit__ = MagicMock(return_value=False)
    return AIAgent(
        completion_service=completion_service,
        trace_manager=trace_manager,
        tool_description=_make_tool_description("agent"),
        component_attributes=ComponentAttributes(
            component_instance_name="test_agent",
            component_instance_id=None,
        ),
        agent_tools=agent_tools,
        skip_tools_with_missing_oauth=skip_tools_with_missing_oauth,
    )


def _make_tool(name: str, available: bool) -> MagicMock:
    tool = MagicMock()
    tool.is_available.return_value = available
    tool.get_tool_descriptions.return_value = [_make_tool_description(name)]
    tool.component_attributes.component_instance_name = name
    return tool


def test_unavailable_tool_skipped_when_flag_enabled():
    available = _make_tool("slack", available=True)
    unavailable = _make_tool("gmail", available=False)

    agent = _make_ai_agent([available, unavailable], skip_tools_with_missing_oauth=True)

    assert "slack" in agent._tool_registry
    assert "gmail" not in agent._tool_registry


def test_unavailable_tool_included_when_flag_disabled():
    available = _make_tool("slack", available=True)
    unavailable = _make_tool("gmail", available=False)

    agent = _make_ai_agent([available, unavailable], skip_tools_with_missing_oauth=False)

    assert "slack" in agent._tool_registry
    assert "gmail" in agent._tool_registry


def test_available_tool_always_included():
    tool = _make_tool("hubspot", available=True)

    agent = _make_ai_agent([tool], skip_tools_with_missing_oauth=True)

    assert "hubspot" in agent._tool_registry


def test_is_available_not_called_when_flag_disabled():
    tool = _make_tool("slack", available=False)

    _make_ai_agent([tool], skip_tools_with_missing_oauth=False)

    tool.is_available.assert_not_called()


def test_no_tools_skipped_when_all_available():
    tools = [_make_tool(name, available=True) for name in ("slack", "gmail", "outlook")]

    agent = _make_ai_agent(tools, skip_tools_with_missing_oauth=True)

    assert set(agent._tool_registry.keys()) == {"slack", "gmail", "outlook"}
