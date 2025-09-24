import json
from unittest.mock import MagicMock, patch, AsyncMock
from types import SimpleNamespace

import pytest

from engine.agent.react_function_calling import ReActAgent, INITIAL_PROMPT, DEFAULT_FALLBACK_REACT_ANSWER
from engine.agent.types import AgentPayload, ToolDescription, ChatMessage, ComponentAttributes
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

    assert output.last_message.content == "Test response"
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
    assert output.last_message.content == "Final response"
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
    mock_llm_service.function_call_async.assert_called_once()
    called_messages = mock_llm_service.function_call_async.call_args.kwargs["messages"]
    assert called_messages[0]["role"] == "system"
    assert called_messages[0]["content"] == INITIAL_PROMPT


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


@patch("engine.prometheus_metric.get_tracing_span")
@patch("engine.prometheus_metric.agent_calls")
def test_date_in_system_prompt_enabled(
    agent_calls_mock, get_span_mock, mock_trace_manager, mock_tool_description, mock_llm_service, agent_input
):
    """Test that date is included in system prompt when date_in_system_prompt is enabled."""
    get_span_mock.return_value.project_id = "1234"
    counter_mock = MagicMock()
    agent_calls_mock.labels.return_value = counter_mock

    react_agent = ReActAgent(
        completion_service=mock_llm_service,
        component_attributes=ComponentAttributes(component_instance_name="Test React Agent With Date"),
        trace_manager=mock_trace_manager,
        tool_description=mock_tool_description,
        date_in_system_prompt=True,
    )

    with patch("engine.agent.react_function_calling.datetime") as mock_datetime:
        mock_datetime.now.return_value.strftime.return_value = "2024-01-15 10:30:00"

        react_agent.run_sync(agent_input)

        # Check that the system message contains the date at the beginning
        mock_llm_service.function_call_async.assert_called_once()
        called_messages = mock_llm_service.function_call_async.call_args.kwargs["messages"]
        system_message = called_messages[0]
        assert system_message["role"] == "system"
        assert system_message.get("content").startswith("Current date and time: 2024-01-15 10:30:00")
        assert INITIAL_PROMPT in system_message.get("content")


@patch("engine.prometheus_metric.get_tracing_span")
@patch("engine.prometheus_metric.agent_calls")
def test_date_in_system_prompt_disabled(
    agent_calls_mock, get_span_mock, mock_trace_manager, mock_tool_description, mock_llm_service, agent_input
):
    """Test that date is not included in system prompt when date_in_system_prompt is disabled."""
    get_span_mock.return_value.project_id = "1234"
    counter_mock = MagicMock()
    agent_calls_mock.labels.return_value = counter_mock

    react_agent = ReActAgent(
        completion_service=mock_llm_service,
        component_attributes=ComponentAttributes(component_instance_name="Test React Agent Without Date"),
        trace_manager=mock_trace_manager,
        tool_description=mock_tool_description,
        date_in_system_prompt=False,
    )

    react_agent.run_sync(agent_input)

    # Check that the system message does not contain the date
    mock_llm_service.function_call_async.assert_called_once()
    called_messages = mock_llm_service.function_call_async.call_args.kwargs["messages"]
    system_message = called_messages[0]
    assert system_message["role"] == "system"
    assert "Current date and time:" not in system_message.get("content")
    assert system_message.get("content") == INITIAL_PROMPT


@patch("engine.prometheus_metric.get_tracing_span")
@patch("engine.prometheus_metric.agent_calls")
def test_structured_output_react_agent(
    agent_calls_mock, get_span_mock, mock_trace_manager, mock_tool_description, mock_llm_service, agent_input
):
    """Test structured output functionality in ReActAgent with various scenarios."""
    get_span_mock.return_value.project_id = "1234"
    counter_mock = MagicMock()
    agent_calls_mock.labels.return_value = counter_mock

    output_tool_properties = {
        "answer": {
            "type": "string",
            "description": "The answer or response content for the user's question or request.",
        },
        "is_ending_conversation": {
            "type": "boolean",
            "description": "Whether this response should end the conversation (true) "
            "or allow for follow-up questions (false).",
        },
    }

    # Scenario A: Normal structured output flow
    react_agent = ReActAgent(
        completion_service=mock_llm_service,
        component_attributes=ComponentAttributes(component_instance_name="Test Structured Output Agent"),
        trace_manager=mock_trace_manager,
        tool_description=mock_tool_description,
        output_tool_name="final_answer",
        output_tool_description="Provide the final structured answer",
        output_tool_properties=output_tool_properties,
        output_tool_required_properties=["answer", "is_ending_conversation"],
        max_iterations=1,
    )

    # Mock LLM to return output tool call
    mock_tool_call = MagicMock()
    mock_tool_call.id = "output_1"
    mock_tool_call.function.name = "final_answer"
    mock_tool_call.function.arguments = json.dumps(
        {"answer": "This is the final answer", "is_ending_conversation": True}
    )

    mock_message = MagicMock()
    mock_message.content = None
    mock_message.tool_calls = [mock_tool_call]
    mock_message.model_dump = lambda: {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "output_1",
                "function": {
                    "name": "final_answer",
                    "arguments": json.dumps({"answer": "This is the final answer", "is_ending_conversation": True}),
                },
            }
        ],
    }

    mock_llm_service.function_call_async = AsyncMock(return_value=MagicMock(choices=[MagicMock(message=mock_message)]))

    output = react_agent.run_sync(agent_input)

    # Verify structured output is returned
    assert output.is_final
    assert output.last_message.content == json.dumps(
        {"answer": "This is the final answer", "is_ending_conversation": True}
    )

    # Scenario B: Max iterations reached with output tool
    react_agent._current_iteration = 1  # At max iterations
    output = react_agent.run_sync(agent_input)
    assert output.is_final
    assert "answer" in output.last_message.content

    # Scenario C: String vs Dict tool properties
    react_agent_str = ReActAgent(
        completion_service=mock_llm_service,
        component_attributes=ComponentAttributes(component_instance_name="Test String Properties"),
        trace_manager=mock_trace_manager,
        tool_description=mock_tool_description,
        output_tool_name="final_answer",
        output_tool_description="Test with string properties",
        output_tool_properties=json.dumps(output_tool_properties),  # String format
        output_tool_required_properties=["answer"],
    )

    # Verify string properties are parsed correctly
    assert react_agent_str._output_tool_agent_description is not None
    assert react_agent_str._output_tool_agent_description.tool_properties == output_tool_properties

    # Scenario D: Output tool with other tools
    mock_other_tool = MagicMock()
    mock_other_tool.tool_description.name = "other_tool"

    react_agent_with_tools = ReActAgent(
        completion_service=mock_llm_service,
        component_attributes=ComponentAttributes(component_instance_name="Test With Other Tools"),
        trace_manager=mock_trace_manager,
        tool_description=mock_tool_description,
        agent_tools=[mock_other_tool],
        output_tool_name="final_answer",
        output_tool_description="Test with other tools",
        output_tool_properties=output_tool_properties,
    )

    # Mock the function_call_async to track the tools and tool_choice parameters
    with patch.object(react_agent_with_tools._completion_service, "function_call_async") as mock_function_call:
        mock_empty_message = MagicMock()
        mock_empty_message.content = "Final response"
        mock_empty_message.tool_calls = []
        mock_empty_message.model_dump = lambda: {"role": "assistant", "content": "Final response", "tool_calls": []}

        mock_function_call.return_value = MagicMock(choices=[MagicMock(message=mock_empty_message)])

        # Run the agent to trigger the tool selection logic
        react_agent_with_tools.run_sync(agent_input)

        # Verify the function was called with correct parameters
        mock_function_call.assert_called_once()
        call_args = mock_function_call.call_args

        # Check that available_tools includes both the other tool and output tool
        available_tools = call_args.kwargs["tools"]
        assert len(available_tools) == 2
        tool_names = [tool.name for tool in available_tools]
        assert "other_tool" in tool_names
        assert "final_answer" in tool_names

        # Check that tool_choice is set to "required"
        assert call_args.kwargs["tool_choice"] == "required"


def test_structured_output_edge_cases(mock_trace_manager, mock_tool_description, mock_llm_service):
    """Test edge cases and error handling for structured output configuration."""

    # Test missing output_tool_name
    with pytest.raises(
        ValueError, match="Error missing critical fields to define output structured output \\['output_tool_name'\\]"
    ):
        ReActAgent(
            completion_service=mock_llm_service,
            component_attributes=ComponentAttributes(component_instance_name="Test Missing Name"),
            trace_manager=mock_trace_manager,
            tool_description=mock_tool_description,
            output_tool_description="Test description",
            output_tool_properties={"test": {"type": "string", "description": "test"}},
        )

    # Test missing output_tool_description
    with pytest.raises(
        ValueError,
        match="Error missing critical fields to define output structured output \\['output_tool_description'\\]",
    ):
        ReActAgent(
            completion_service=mock_llm_service,
            component_attributes=ComponentAttributes(component_instance_name="Test Missing Description"),
            trace_manager=mock_trace_manager,
            tool_description=mock_tool_description,
            output_tool_name="test_tool",
            output_tool_properties={"test": {"type": "string", "description": "test"}},
        )

    # Test missing output_tool_properties
    with pytest.raises(
        ValueError,
        match="Error missing critical fields to define output structured output \\['output_tool_properties'\\]",
    ):
        ReActAgent(
            completion_service=mock_llm_service,
            component_attributes=ComponentAttributes(component_instance_name="Test Missing Properties"),
            trace_manager=mock_trace_manager,
            tool_description=mock_tool_description,
            output_tool_name="test_tool",
            output_tool_description="Test description",
        )

    # Test missing multiple fields
    with pytest.raises(
        ValueError,
        match="Error missing critical fields to define output structured output"
        " \\['output_tool_name', 'output_tool_description'\\]",
    ):
        ReActAgent(
            completion_service=mock_llm_service,
            component_attributes=ComponentAttributes(component_instance_name="Test Missing Multiple"),
            trace_manager=mock_trace_manager,
            tool_description=mock_tool_description,
            output_tool_properties={"test": {"type": "string", "description": "test"}},
        )

    # Test invalid JSON in output_tool_properties string
    with pytest.raises(ValueError, match="Failed to parse data"):
        ReActAgent(
            completion_service=mock_llm_service,
            component_attributes=ComponentAttributes(component_instance_name="Test Invalid JSON"),
            trace_manager=mock_trace_manager,
            tool_description=mock_tool_description,
            output_tool_name="test_tool",
            output_tool_description="Test description",
            output_tool_properties='{"invalid": json}',  # Invalid JSON
        )

    # Test invalid JSON in output_tool_required_properties string
    with pytest.raises(ValueError, match="Failed to parse data"):
        ReActAgent(
            completion_service=mock_llm_service,
            component_attributes=ComponentAttributes(component_instance_name="Test Invalid Required JSON"),
            trace_manager=mock_trace_manager,
            tool_description=mock_tool_description,
            output_tool_name="test_tool",
            output_tool_description="Test description",
            output_tool_properties={"test": {"type": "string", "description": "test"}},
            output_tool_required_properties='["invalid", json]',  # Invalid JSON
        )
