import json
from unittest.mock import MagicMock, AsyncMock
from types import SimpleNamespace

import pytest

from engine.agent.react_function_calling import ReActAgent
from engine.agent.agent import AgentPayload, ToolDescription, ChatMessage
from engine.trace.trace_manager import TraceManager


class MockToolCall:
    """Mock tool call object used across multiple ReAct agent tests."""

    def __init__(self, tool_id="1", tool_name="test_tool", arguments=None):
        if arguments is None:
            arguments = {"test_property": "Test value"}

        self.id = tool_id
        self.function = SimpleNamespace(name=tool_name, arguments=json.dumps(arguments))
        self.type = "function"

    def model_dump(self):
        return {
            "id": self.id,
            "function": {"name": self.function.name, "arguments": self.function.arguments},
            "type": self.type,
        }


async def mock_process_tool_calls(*args, **kwargs):
    """Mock implementation of _process_tool_calls method."""
    tool_outputs = {
        "1": AgentPayload(messages=[ChatMessage(role="assistant", content="Tool response")], is_final=True)
    }
    processed_tool_calls = [
        {
            "id": "1",
            "function": {"name": "test_tool", "arguments": json.dumps({"test_property": "Test value"})},
            "type": "function",
        }
    ]
    return tool_outputs, processed_tool_calls


@pytest.fixture
def mock_agent():
    """Mock agent fixture for ReAct agent tests."""
    mock_agent = MagicMock(spec=ReActAgent)
    mock_tool_description = MagicMock(spec=ToolDescription)
    mock_tool_description.name = "test_tool"
    mock_tool_description.description = "Test tool description"
    mock_tool_description.tool_properties = {
        "test_property": {"type": "string", "description": "Test property description"}
    }
    mock_tool_description.required_tool_properties = ["test_property"]
    mock_agent.tool_description = mock_tool_description
    mock_agent.run = AsyncMock()
    return mock_agent


@pytest.fixture
def mock_trace_manager():
    """Mock trace manager fixture."""
    return MagicMock(spec=TraceManager)


@pytest.fixture
def mock_tool_description():
    """Mock tool description fixture."""
    tool_description = MagicMock(spec=ToolDescription)
    tool_description.name = "test_tool"
    tool_description.description = "Test tool description"
    tool_description.tool_properties = {
        "test_property": {"type": "string", "description": "Test property description"}
    }
    tool_description.required_tool_properties = ["test_property"]
    return tool_description


@pytest.fixture
def agent_input():
    """Basic agent input fixture."""
    return AgentPayload(messages=[ChatMessage(role="user", content="Test message")])


@pytest.fixture
def react_agent(mock_agent, mock_trace_manager, mock_tool_description, mock_llm_service):
    """ReAct agent fixture with all dependencies."""
    return ReActAgent(
        completion_service=mock_llm_service,
        component_instance_name="Test React Agent",
        agent_tools=[mock_agent],
        trace_manager=mock_trace_manager,
        tool_description=mock_tool_description,
    )


@pytest.fixture
def react_agent_with_tool_calls(
    mock_agent, mock_trace_manager, mock_tool_description, mock_llm_service_with_tool_calls
):
    """ReAct agent fixture configured for tool call testing."""
    return ReActAgent(
        completion_service=mock_llm_service_with_tool_calls,
        component_instance_name="Test React Agent With Tool Calls",
        agent_tools=[mock_agent],
        trace_manager=mock_trace_manager,
        tool_description=mock_tool_description,
    )


@pytest.fixture
def react_agent_sequential(mock_agent, mock_trace_manager, mock_tool_description, mock_llm_service_sequential):
    """ReAct agent fixture configured for sequential response testing."""
    return ReActAgent(
        completion_service=mock_llm_service_sequential,
        component_instance_name="Test React Agent Sequential",
        agent_tools=[mock_agent],
        trace_manager=mock_trace_manager,
        tool_description=mock_tool_description,
    )
