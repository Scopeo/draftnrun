import json
from unittest.mock import MagicMock, patch, AsyncMock
from types import SimpleNamespace

import pytest

from engine.agent.react_function_calling import ReActAgent, INITIAL_PROMPT, DEFAULT_FALLBACK_REACT_ANSWER
from engine.agent.data_structures import AgentPayload, ToolDescription, ChatMessage, ComponentAttributes
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
    mock_llm_service.function_call_async = AsyncMock(return_value=response)
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

    assert output.content == "Test response"
    assert output.is_final


@patch("engine.prometheus_metric.get_tracing_span")
@patch("engine.prometheus_metric.agent_calls")
def test_run_with_tool_calls(agent_calls_mock, get_span_mock, react_agent, agent_input, mock_agent, mock_llm_service):
    get_span_mock.return_value.project_id = "1234"
    counter_mock = MagicMock()
    agent_calls_mock.labels.return_value = counter_mock
    mock_tool_call = MagicMock()
    mock_tool_call.id = "1"
    mock_tool_call_function = MagicMock()
    mock_tool_call_function.name = "test_tool"
    mock_tool_call_function.arguments = json.dumps({"test_property": "Test value"})
    mock_tool_call.function = mock_tool_call_function
    mock_response_message = ChatMessage(role="assistant", content="Tool response")

    mock_llm_service.function_call_async = AsyncMock(
        return_value=MagicMock(choices=[MagicMock(message=mock_response_message, tool_calls=[mock_tool_call])])
    )
    mock_agent.run.return_value = AgentPayload(
        messages=[ChatMessage(role="assistant", content="Tool response")], is_final=True
    )

    output = react_agent.run_sync(agent_input)

    assert output.content == "Tool response"
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

    mock_agent.run.return_value = AgentPayload(
        messages=[ChatMessage(role="assistant", content="Tool response")], is_final=True
    )

    # Mock the LLM service to return different responses for each call
    # First call: with tool calls, second call: final response
    first_response = MagicMock()
    first_response.choices = [
        MagicMock(
            message=MagicMock(
                content=None,
                tool_calls=[MagicMock()],
                model_dump=lambda: {"role": "assistant", "content": None, "tool_calls": [{"id": "1"}]},
            )
        )
    ]

    second_response = MagicMock()
    second_response.choices = [
        MagicMock(
            message=MagicMock(
                content="Final response",
                tool_calls=[],
                model_dump=lambda: {"role": "assistant", "content": "Final response", "tool_calls": []},
            )
        )
    ]

    mock_llm_service.function_call_async = AsyncMock(side_effect=[first_response, second_response])

    # Mock the tool call processing to simulate successful tool execution
    with patch.object(react_agent, "_process_tool_calls") as mock_process:
        mock_process.return_value = (
            {"1": AgentPayload(messages=[ChatMessage(role="assistant", content="Tool response")], is_final=True)},
            [
                {
                    "id": "1",
                    "function": {"name": "test_tool", "arguments": json.dumps({"test_property": "Test value"})},
                    "type": "function",
                }
            ],
        )

        output = react_agent.run_sync(agent_input)

    # Should get the final response from the second iteration
    assert output.content == "Final response"
    assert output.is_final
    # Verify that function_call_async was called twice (once for tool calls, once for final response)
    assert react_agent._completion_service.function_call_async.call_count == 2


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
    mock_tool_call = MagicMock()
    mock_tool_call.id = "1"
    mock_tool_call_function = MagicMock()
    mock_tool_call_function.name = "test_tool"
    mock_tool_call_function.arguments = json.dumps({"test_property": "Test value"})
    message = SimpleNamespace(
        role="assistant",
        tool_calls=mock_tool_call,
        model_dump=lambda: {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "1",
                    "function": {"name": "test_tool", "arguments": json.dumps({"test_property": "Test value"})},
                }
            ],
        },
    )
    choice = SimpleNamespace(message=message)
    response = SimpleNamespace(choices=[choice])
    mock_llm_service.function_call_async = AsyncMock(return_value=response)

    react_agent._max_iterations = 1
    mock_agent.run.return_value = AgentPayload(
        messages=[ChatMessage(role="assistant", content="Tool response")], is_final=False
    )

    output = react_agent.run_sync(agent_input)

    assert output.content == DEFAULT_FALLBACK_REACT_ANSWER
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
