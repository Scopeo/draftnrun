import json
from unittest.mock import MagicMock, patch, AsyncMock
from types import SimpleNamespace

import pytest

from engine.agent.react_function_calling import ReActAgent, INITIAL_PROMPT, DEFAULT_FALLBACK_REACT_ANSWER
from engine.agent.agent import AgentPayload, ComponentAttributes, ToolDescription, ChatMessage
from engine.trace.trace_manager import TraceManager
from engine.llm_services.llm_service import CompletionService


@pytest.fixture
def mock_agent():
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
    return MagicMock(spec=TraceManager)


@pytest.fixture
def mock_tool_description():
    tool_description = MagicMock(spec=ToolDescription)
    tool_description.name = "test_tool"
    tool_description.description = "Test tool description"
    tool_description.tool_properties = {
        "test_property": {"type": "string", "description": "Test property description"}
    }
    tool_description.required_tool_properties = ["test_property"]
    return tool_description


@pytest.fixture
def mock_llm_service():
    mock_llm_service = MagicMock(spec=CompletionService)
    mock_llm_service._model_name = "test_model"
    message = SimpleNamespace(
        role="assistant",
        content="Test response",
        tool_calls=[],
        model_dump=lambda: {"role": "assistant", "content": "Test response", "tool_calls": []},
    )

    choice = SimpleNamespace(message=message)
    response = SimpleNamespace(choices=[choice])

    mock_llm_service.afunction_call = AsyncMock(return_value=response)
    return mock_llm_service


@pytest.fixture
def agent_input():
    return AgentPayload(messages=[ChatMessage(role="user", content="Test message")])


@pytest.fixture
def react_agent(mock_agent, mock_trace_manager, mock_tool_description, mock_llm_service):
    return ReActAgent(
        completion_service=mock_llm_service,
        component_attributes=ComponentAttributes(component_instance_name="Test React Agent"),
        agent_tools=[mock_agent],
        trace_manager=mock_trace_manager,
        tool_description=mock_tool_description,
    )


@patch("engine.prometheus_metric.get_tracing_span")
@patch("engine.prometheus_metric.agent_calls")
def test_run_no_tool_calls(agent_calls_mock, get_span_mock, react_agent, agent_input, mock_llm_service):
    get_span_mock.return_value.project_id = "1234"
    counter_mock = MagicMock()
    agent_calls_mock.labels.return_value = counter_mock

    output = react_agent.run_sync(agent_input)

    assert output.last_message.content == "Test response"
    assert output.is_final


@patch("engine.prometheus_metric.get_tracing_span")
@patch("engine.prometheus_metric.agent_calls")
def test_run_with_tool_calls(agent_calls_mock, get_span_mock, react_agent, agent_input, mock_agent, mock_llm_service):
    get_span_mock.return_value.project_id = "1234"
    counter_mock = MagicMock()
    agent_calls_mock.labels.return_value = counter_mock

    # Enable tool shortcuts so that when there's exactly one successful output, it returns it
    react_agent._allow_tool_shortcuts = True

    # Create a simple object that has the required attributes
    class MockToolCall:
        def __init__(self):
            self.id = "1"
            self.function = SimpleNamespace(name="test_tool", arguments=json.dumps({"test_property": "Test value"}))
            self.type = "function"

        def model_dump(self):
            return {
                "id": "1",
                "function": {"name": "test_tool", "arguments": json.dumps({"test_property": "Test value"})},
                "type": "function",
            }

    mock_tool_call = MockToolCall()

    mock_message = SimpleNamespace(
        role="assistant",
        content="Tool response",
        tool_calls=[mock_tool_call],
        model_dump=lambda: {
            "role": "assistant",
            "content": "Tool response",
            "tool_calls": [
                {
                    "id": "1",
                    "function": {"name": "test_tool", "arguments": json.dumps({"test_property": "Test value"})},
                    "type": "function",
                }
            ],
        },
    )

    mock_choice = SimpleNamespace(message=mock_message)
    mock_response = SimpleNamespace(choices=[mock_choice])

    mock_llm_service.afunction_call.return_value = mock_response
    mock_agent.run.return_value = AgentPayload(
        messages=[ChatMessage(role="assistant", content="Tool response")], is_final=True
    )

    # Patch the _process_tool_calls method to return dictionaries instead of MockToolCall objects
    async def mock_process_tool_calls(*args, **kwargs):
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

    with patch.object(react_agent, "_process_tool_calls", side_effect=mock_process_tool_calls):
        output = react_agent.run_sync(agent_input)

    assert output.last_message.role == "assistant"
    assert output.last_message.content == "Tool response"
    assert output.is_final


@patch("engine.prometheus_metric.get_tracing_span")
@patch("engine.prometheus_metric.agent_calls")
def test_run_with_tool_calls_no_shortcut(
    agent_calls_mock, get_span_mock, react_agent, agent_input, mock_agent, mock_llm_service
):
    get_span_mock.return_value.project_id = "1234"
    counter_mock = MagicMock()
    agent_calls_mock.labels.return_value = counter_mock

    # Disable tool shortcuts to test the full iteration logic
    react_agent._allow_tool_shortcuts = False

    # Create a simple object that has the required attributes
    class MockToolCall:
        def __init__(self):
            self.id = "1"
            self.function = SimpleNamespace(name="test_tool", arguments=json.dumps({"test_property": "Test value"}))
            self.type = "function"

        def model_dump(self):
            return {
                "id": "1",
                "function": {"name": "test_tool", "arguments": json.dumps({"test_property": "Test value"})},
                "type": "function",
            }

    mock_tool_call = MockToolCall()

    # First call: return tool calls
    mock_message_with_tools = SimpleNamespace(
        role="assistant",
        content="Tool response",
        tool_calls=[mock_tool_call],
        model_dump=lambda: {
            "role": "assistant",
            "content": "Tool response",
            "tool_calls": [
                {
                    "id": "1",
                    "function": {"name": "test_tool", "arguments": json.dumps({"test_property": "Test value"})},
                    "type": "function",
                }
            ],
        },
    )

    # Second call: return no tool calls (final response)
    mock_message_final = SimpleNamespace(
        role="assistant",
        content="Final response",
        tool_calls=[],
        model_dump=lambda: {
            "role": "assistant",
            "content": "Final response",
            "tool_calls": [],
        },
    )

    mock_choice_with_tools = SimpleNamespace(message=mock_message_with_tools)
    mock_choice_final = SimpleNamespace(message=mock_message_final)
    mock_response_with_tools = SimpleNamespace(choices=[mock_choice_with_tools])
    mock_response_final = SimpleNamespace(choices=[mock_choice_final])

    # Set up the mock to return different responses on subsequent calls
    mock_llm_service.afunction_call.side_effect = [mock_response_with_tools, mock_response_final]

    mock_agent.run.return_value = AgentPayload(
        messages=[ChatMessage(role="assistant", content="Tool response")], is_final=True
    )

    # Patch the _process_tool_calls method to return dictionaries instead of MockToolCall objects
    async def mock_process_tool_calls(*args, **kwargs):
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

    with patch.object(react_agent, "_process_tool_calls", side_effect=mock_process_tool_calls):
        output = react_agent.run_sync(agent_input)

    # Should get the final response from the second iteration
    assert output.last_message.role == "assistant"
    assert output.last_message.content == "Final response"
    assert output.is_final
    # Verify that afunction_call was called twice (once for tool calls, once for final response)
    assert mock_llm_service.afunction_call.call_count == 2


@patch("engine.prometheus_metric.get_tracing_span")
@patch("engine.prometheus_metric.agent_calls")
def test_initial_prompt_insertion(agent_calls_mock, get_span_mock, react_agent, agent_input, mock_llm_service):
    get_span_mock.return_value.project_id = "1234"
    counter_mock = MagicMock()
    agent_calls_mock.labels.return_value = counter_mock

    react_agent.run_sync(agent_input)
    assert agent_input.messages[0].role == "system"
    assert agent_input.messages[0].content == INITIAL_PROMPT


@patch("engine.prometheus_metric.get_tracing_span")
@patch("engine.prometheus_metric.agent_calls")
def test_max_iterations(agent_calls_mock, get_span_mock, react_agent, agent_input, mock_agent, mock_llm_service):
    get_span_mock.return_value.project_id = "1234"
    counter_mock = MagicMock()
    agent_calls_mock.labels.return_value = counter_mock

    # Create a simple object that has the required attributes
    class MockToolCall:
        def __init__(self):
            self.id = "1"
            self.function = SimpleNamespace(name="test_tool", arguments=json.dumps({"test_property": "Test value"}))
            self.type = "function"

        def model_dump(self):
            return {
                "id": "1",
                "function": {"name": "test_tool", "arguments": json.dumps({"test_property": "Test value"})},
                "type": "function",
            }

    mock_tool_call = MockToolCall()

    mock_message = SimpleNamespace(
        role="assistant",
        tool_calls=[mock_tool_call],
        model_dump=lambda: {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "1",
                    "function": {"name": "test_tool", "arguments": json.dumps({"test_property": "Test value"})},
                    "type": "function",
                }
            ],
        },
    )

    mock_choice = SimpleNamespace(message=mock_message)
    mock_response = SimpleNamespace(choices=[mock_choice])

    mock_llm_service.afunction_call.return_value = mock_response

    react_agent._max_iterations = 1
    mock_agent.run.return_value = AgentPayload(
        messages=[ChatMessage(role="assistant", content="Tool response")], is_final=False
    )

    # Patch the _process_tool_calls method to return dictionaries instead of MockToolCall objects
    async def mock_process_tool_calls(*args, **kwargs):
        tool_outputs = {
            "1": AgentPayload(messages=[ChatMessage(role="assistant", content="Tool response")], is_final=False)
        }
        processed_tool_calls = [
            {
                "id": "1",
                "function": {"name": "test_tool", "arguments": json.dumps({"test_property": "Test value"})},
                "type": "function",
            }
        ]
        return tool_outputs, processed_tool_calls

    with patch.object(react_agent, "_process_tool_calls", side_effect=mock_process_tool_calls):
        output = react_agent.run_sync(agent_input)

    assert output.last_message.content == DEFAULT_FALLBACK_REACT_ANSWER
    assert not output.is_final


def test_react_agent_without_tools(mock_trace_manager, mock_tool_description, mock_llm_service):
    """Test that ReActAgent can be instantiated without tools."""
    react_agent = ReActAgent(
        completion_service=mock_llm_service,
        component_attributes=ComponentAttributes(component_instance_name="Test React Agent Without Tools"),
        trace_manager=mock_trace_manager,
        tool_description=mock_tool_description,
    )

    assert react_agent.agent_tools == []
    assert react_agent.component_attributes.component_instance_name == "Test React Agent Without Tools"
    assert react_agent._max_iterations == 3
    assert react_agent.initial_prompt == INITIAL_PROMPT
