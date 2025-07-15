from unittest.mock import patch


from engine.agent.react_function_calling import ReActAgent, INITIAL_PROMPT, DEFAULT_FALLBACK_REACT_ANSWER
from engine.agent.agent import AgentPayload, ComponentAttributes, ToolDescription, ChatMessage
from engine.trace.trace_manager import TraceManager
from engine.llm_services.llm_service import CompletionService
from engine.agent.react_function_calling import ReActAgent, INITIAL_PROMPT
from engine.agent.agent import AgentPayload, ChatMessage


# Import shared mocks
from tests.mocks.react_agent import (
    mock_process_tool_calls,
)


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
# Import prometheus metrics mocks
from tests.mocks.prometheus_metrics import (
    setup_prometheus_mocks,
)


@patch("engine.prometheus_metric.get_tracing_span")
@patch("engine.prometheus_metric.agent_calls")
def test_run_no_tool_calls(agent_calls_mock, get_span_mock, react_agent, agent_input, mock_llm_service):
    setup_prometheus_mocks(get_span_mock, agent_calls_mock)

    output = react_agent.run_sync(agent_input)

    assert output.last_message.content == "Test response"
    assert output.is_final


@patch("engine.prometheus_metric.get_tracing_span")
@patch("engine.prometheus_metric.agent_calls")
def test_run_with_tool_calls(agent_calls_mock, get_span_mock, react_agent_with_tool_calls, agent_input, mock_agent):
    setup_prometheus_mocks(get_span_mock, agent_calls_mock)

    # Enable tool shortcuts so that when there's exactly one successful output, it returns it
    react_agent_with_tool_calls._allow_tool_shortcuts = True

    mock_agent.run.return_value = AgentPayload(
        messages=[ChatMessage(role="assistant", content="Tool response")], is_final=True
    )

    with patch.object(react_agent_with_tool_calls, "_process_tool_calls", side_effect=mock_process_tool_calls):
        output = react_agent_with_tool_calls.run_sync(agent_input)

    assert output.last_message.role == "assistant"
    assert output.last_message.content == "Tool response"
    assert output.is_final


@patch("engine.prometheus_metric.get_tracing_span")
@patch("engine.prometheus_metric.agent_calls")
def test_run_with_tool_calls_no_shortcut(
    agent_calls_mock, get_span_mock, react_agent_sequential, agent_input, mock_agent
):
    setup_prometheus_mocks(get_span_mock, agent_calls_mock)

    # Disable tool shortcuts to test the full iteration logic
    react_agent_sequential._allow_tool_shortcuts = False

    mock_agent.run.return_value = AgentPayload(
        messages=[ChatMessage(role="assistant", content="Tool response")], is_final=True
    )

    with patch.object(react_agent_sequential, "_process_tool_calls", side_effect=mock_process_tool_calls):
        output = react_agent_sequential.run_sync(agent_input)

    # Should get the final response from the second iteration
    assert output.last_message.role == "assistant"
    assert output.last_message.content == "Final response"
    assert output.is_final
    # Verify that afunction_call was called twice (once for tool calls, once for final response)
    assert react_agent_sequential._completion_service.afunction_call.call_count == 2


@patch("engine.prometheus_metric.get_tracing_span")
@patch("engine.prometheus_metric.agent_calls")
def test_initial_prompt_insertion(agent_calls_mock, get_span_mock, react_agent, agent_input, mock_llm_service):
    setup_prometheus_mocks(get_span_mock, agent_calls_mock)

    react_agent.run_sync(agent_input)
    assert agent_input.messages[0].role == "system"
    assert agent_input.messages[0].content == INITIAL_PROMPT


@patch("engine.prometheus_metric.get_tracing_span")
@patch("engine.prometheus_metric.agent_calls")
def test_max_iterations(agent_calls_mock, get_span_mock, react_agent_with_tool_calls, agent_input, mock_agent):
    setup_prometheus_mocks(get_span_mock, agent_calls_mock)

    react_agent_with_tool_calls._max_iterations = 1
    mock_agent.run.return_value = AgentPayload(
        messages=[ChatMessage(role="assistant", content="Tool response")], is_final=False
    )

    with patch.object(react_agent_with_tool_calls, "_process_tool_calls", side_effect=mock_process_tool_calls):
        output = react_agent_with_tool_calls.run_sync(agent_input)

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
