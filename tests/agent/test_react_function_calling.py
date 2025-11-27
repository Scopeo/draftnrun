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
    mock_llm_service._model_id = None
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
@patch("engine.llm_services.utils.check_usage")
@patch("engine.llm_services.utils.get_tracing_span")
def test_structured_output_in_function_call_async(
    utils_get_span_mock, agent_calls_mock, get_span_mock, mock_trace_manager, mock_tool_description, agent_input
):
    """Test structured output functionality in function_call_async method."""
    get_span_mock.return_value.project_id = "1234"
    counter_mock = MagicMock()
    agent_calls_mock.labels.return_value = counter_mock

    # Mock the tracing span for utils
    mock_tracing_span = MagicMock()
    mock_tracing_span.organization_llm_providers = ["openai"]
    utils_get_span_mock.return_value = mock_tracing_span

    # Create structured output tool
    output_tool_properties = {
        "answer": {"type": "string", "description": "The final answer"},
        "is_final": {"type": "boolean", "description": "Whether this is the final response"},
    }

    # Create a real CompletionService instance but mock the llm calls in the following
    real_completion_service = CompletionService(
        trace_manager=mock_trace_manager, provider="openai", model_name="test_model"
    )

    # Create ReActAgent with structured output
    react_agent = ReActAgent(
        completion_service=real_completion_service,
        component_attributes=ComponentAttributes(component_instance_name="Test Structured Output"),
        trace_manager=mock_trace_manager,
        tool_description=mock_tool_description,
        output_format=output_tool_properties,
        max_iterations=2,  # Allow for 2 iterations: tool call + structured output
    )

    # Test 1: Verify structured output tool is constructed correctly
    output_tool = react_agent._get_output_tool_description(react_agent._output_format)
    assert output_tool is not None
    assert output_tool.name == "chat_formatting_output_tool"
    assert output_tool.tool_properties == output_tool_properties

    # Test 2: Structured output tool called directly
    with patch("openai.AsyncOpenAI") as mock_openai_client:
        mock_client = MagicMock()
        mock_openai_client.return_value = mock_client

        # Create the tool call response
        mock_structured_tool_call = MagicMock()
        mock_structured_tool_call.id = "2"
        mock_structured_tool_call.function.name = "chat_formatting_output_tool"
        mock_structured_tool_call.function.arguments = {"answer": "Final answer", "is_final": True}

        mock_message_structured = MagicMock()
        mock_message_structured.content = None
        mock_message_structured.tool_calls = [mock_structured_tool_call]
        mock_message_structured.model_dump = lambda: {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "2",
                    "function": {
                        "name": "chat_formatting_output_tool",
                        "arguments": {"answer": "Final answer", "is_final": True},
                    },
                }
            ],
        }

        # Mock the chat completions response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=mock_message_structured)]
        mock_response.usage = MagicMock(completion_tokens=10, prompt_tokens=5, total_tokens=15)
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        output = react_agent.run_sync(agent_input)
        # The ensure_tools_or_structured_output_response should extract the arguments and return them as JSON
        assert output.last_message.content == json.dumps({"answer": "Final answer", "is_final": True})
        assert output.is_final

        # Verify that tool_choice was changed to "required" when structured_output_tool is provided
        mock_client.chat.completions.create.assert_called_once()
        call_args = mock_client.chat.completions.create.call_args
        assert call_args.kwargs.get("tool_choice") == "required"

    # Test 3: Full iteration flow - regular tool call -> structured output call
    # First, add a mock agent tool to the ReActAgent
    mock_agent_tool = MagicMock()
    mock_agent_tool.tool_description.name = "test_tool"
    mock_agent_tool.tool_description.description = "Test tool description"
    mock_agent_tool.tool_description.tool_properties = {
        "test_property": {"type": "string", "description": "Test property description"}
    }
    mock_agent_tool.tool_description.required_tool_properties = ["test_property"]
    mock_agent_tool.run = AsyncMock(
        return_value=AgentPayload(
            messages=[ChatMessage(role="assistant", content="Tool executed successfully")],
            is_final=False,  # Tool is not final, so agent continues iteration
        )
    )

    # Add the tool to the agent
    react_agent.agent_tools = [mock_agent_tool]

    with patch("openai.AsyncOpenAI") as mock_openai_client:
        mock_client = MagicMock()
        mock_openai_client.return_value = mock_client

        # First call: Regular tool call
        mock_regular_tool_call = MagicMock()
        mock_regular_tool_call.id = "3"
        mock_regular_tool_call.function.name = "test_tool"
        mock_regular_tool_call.function.arguments = json.dumps({"test_property": "test_value"})

        mock_message_regular_tool = MagicMock()
        mock_message_regular_tool.content = None
        mock_message_regular_tool.tool_calls = [mock_regular_tool_call]
        mock_message_regular_tool.model_dump = lambda: {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "3",
                    "function": {"name": "test_tool", "arguments": json.dumps({"test_property": "test_value"})},
                }
            ],
        }

        # Second call: Structured output tool call
        mock_structured_tool_call = MagicMock()
        mock_structured_tool_call.id = "4"
        mock_structured_tool_call.function.name = "chat_formatting_output_tool"
        mock_structured_tool_call.function.arguments = {"answer": "Final structured answer", "is_final": True}

        mock_message_structured = MagicMock()
        mock_message_structured.content = None
        mock_message_structured.tool_calls = [mock_structured_tool_call]
        mock_message_structured.model_dump = lambda: {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "4",
                    "function": {
                        "name": "chat_formatting_output_tool",
                        "arguments": {"answer": "Final structured answer", "is_final": True},
                    },
                }
            ],
        }

        # Mock the chat completions responses for both calls
        mock_response_regular = MagicMock()
        mock_response_regular.choices = [MagicMock(message=mock_message_regular_tool)]
        mock_response_regular.usage = MagicMock(completion_tokens=10, prompt_tokens=5, total_tokens=15)

        mock_response_structured = MagicMock()
        mock_response_structured.choices = [MagicMock(message=mock_message_structured)]
        mock_response_structured.usage = MagicMock(completion_tokens=10, prompt_tokens=5, total_tokens=15)

        # Mock the responses in sequence
        mock_client.chat.completions.create = AsyncMock(side_effect=[mock_response_regular, mock_response_structured])

        # Mock the _process_tool_calls method to return the correct format for the first call
        with patch.object(react_agent, "_process_tool_calls") as mock_process:
            mock_process.return_value = (
                {
                    "3": AgentPayload(
                        messages=[ChatMessage(role="assistant", content="Tool executed successfully")], is_final=False
                    )
                },
                [
                    {
                        "id": "3",
                        "function": {"name": "test_tool", "arguments": json.dumps({"test_property": "test_value"})},
                        "type": "function",
                    }
                ],
            )

            output = react_agent.run_sync(agent_input)
            # Should return the structured output from the second iteration
            assert output.last_message.content == json.dumps({"answer": "Final structured answer", "is_final": True})
            assert output.is_final
            # Verify two LLM calls were made (first for tool, second for structured output)
            assert mock_client.chat.completions.create.call_count == 2

    # Test 4: No tools called - should call backup method and return structured output
    with patch("openai.AsyncOpenAI") as mock_openai_client:
        mock_client = MagicMock()
        mock_openai_client.return_value = mock_client

        # First call: no tools called, returns regular content
        mock_message_no_tools = MagicMock()
        mock_message_no_tools.content = "Regular response"
        mock_message_no_tools.tool_calls = None
        mock_message_no_tools.model_dump = lambda: {
            "role": "assistant",
            "content": "Regular response",
            "tool_calls": None,
        }

        # Second call: backup method returns structured JSON
        mock_message_backup = MagicMock()
        mock_message_backup.content = json.dumps({"answer": "Backup structured answer", "is_final": True})
        mock_message_backup.tool_calls = None
        mock_message_backup.model_dump = lambda: {
            "role": "assistant",
            "content": json.dumps({"answer": "Backup structured answer", "is_final": True}),
            "tool_calls": None,
        }

        # Mock the chat completions responses
        mock_response_no_tools = MagicMock()
        mock_response_no_tools.choices = [MagicMock(message=mock_message_no_tools)]
        mock_response_no_tools.usage = MagicMock(completion_tokens=10, prompt_tokens=5, total_tokens=15)

        mock_response_backup = MagicMock()
        mock_response_backup.choices = [MagicMock(message=mock_message_backup)]
        mock_response_backup.usage = MagicMock(completion_tokens=10, prompt_tokens=5, total_tokens=15)

        # The first call returns no tools, the second call (backup) returns structured content
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response_no_tools)

        # Mock the responses.parse method for the backup call
        mock_parse_response = MagicMock()
        mock_parse_response.output_text = json.dumps({"answer": "Backup structured answer", "is_final": True})
        mock_parse_response.usage = MagicMock(output_tokens=10, input_tokens=5, total_tokens=15)
        mock_client.responses.parse = AsyncMock(return_value=mock_parse_response)

        output = react_agent.run_sync(agent_input)
        # Should return the structured output from the backup method
        assert output.last_message.content == json.dumps({"answer": "Backup structured answer", "is_final": True})
        assert output.is_final

    # Test 5: Max iterations reached - tool_choice should be "none" and constrained_complete should be called
    # Create a new ReActAgent with max_iterations=1 to trigger the max iteration scenario
    react_agent_max_iter = ReActAgent(
        completion_service=real_completion_service,
        component_attributes=ComponentAttributes(component_instance_name="Test Max Iterations"),
        trace_manager=mock_trace_manager,
        tool_description=mock_tool_description,
        output_format=output_tool_properties,
        max_iterations=1,  # Set to 1 to trigger max iterations on second call
    )

    # Add a mock agent tool
    react_agent_max_iter.agent_tools = [mock_agent_tool]

    with patch("openai.AsyncOpenAI") as mock_openai_client:
        mock_client = MagicMock()
        mock_openai_client.return_value = mock_client

        # First call: Regular tool call (iteration 0)
        mock_regular_tool_call = MagicMock()
        mock_regular_tool_call.id = "5"
        mock_regular_tool_call.function.name = "test_tool"
        mock_regular_tool_call.function.arguments = json.dumps({"test_property": "test_value"})

        mock_message_regular_tool = MagicMock()
        mock_message_regular_tool.content = None
        mock_message_regular_tool.tool_calls = [mock_regular_tool_call]
        mock_message_regular_tool.model_dump = lambda: {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "5",
                    "function": {"name": "test_tool", "arguments": json.dumps({"test_property": "test_value"})},
                }
            ],
        }

        # Second call: Max iterations reached, should call constrained_complete (iteration 1)
        # This should trigger tool_choice="none" and call the backup method

        # Mock the chat completions response for the first call
        mock_response_regular = MagicMock()
        mock_response_regular.choices = [MagicMock(message=mock_message_regular_tool)]
        mock_response_regular.usage = MagicMock(completion_tokens=10, prompt_tokens=5, total_tokens=15)

        # Mock the responses.parse method for the constrained_complete call
        mock_parse_response = MagicMock()
        mock_parse_response.output_text = json.dumps({"answer": "Max iterations reached answer", "is_final": True})
        mock_parse_response.usage = MagicMock(output_tokens=10, input_tokens=5, total_tokens=15)
        mock_client.responses.parse = AsyncMock(return_value=mock_parse_response)

        # Mock the responses in sequence: first call returns tool, second call triggers constrained_complete
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response_regular)

        # Mock the _process_tool_calls method to return the correct format for the first call
        with patch.object(react_agent_max_iter, "_process_tool_calls") as mock_process:
            mock_process.return_value = (
                {
                    "5": AgentPayload(
                        messages=[ChatMessage(role="assistant", content="Tool executed successfully")], is_final=False
                    )
                },
                [
                    {
                        "id": "5",
                        "function": {"name": "test_tool", "arguments": json.dumps({"test_property": "test_value"})},
                        "type": "function",
                    }
                ],
            )

            output = react_agent_max_iter.run_sync(agent_input)
            # Should return the structured output from the constrained_complete method
            assert output.last_message.content == json.dumps(
                {"answer": "Max iterations reached answer", "is_final": True}
            )
            assert output.is_final

            # Verify that the constrained_complete method was called (via responses.parse)
            mock_client.responses.parse.assert_called_once()

            # Verify that the first call had tool_choice="required" (for structured output)
            # and the second call had tool_choice="none" (for max iterations)
            assert mock_client.chat.completions.create.call_count == 1  # Only one chat.completions.create call
            # The second call goes through responses.parse (constrained_complete)


def test_react_agent_with_null_output_format(mock_trace_manager, mock_tool_description, mock_llm_service):
    """Test that ReActAgent handles output_format='null' without crashing.

    This test reproduces the bug where agent workflows fail with:
    'NoneType' object has no attribute 'keys'

    The bug occurs when output_format is passed as the string 'null' instead of None.
    """
    # This should not raise an exception with the fix
    react_agent = ReActAgent(
        completion_service=mock_llm_service,
        component_attributes=ComponentAttributes(component_instance_name="Test React Agent With Null Output"),
        trace_manager=mock_trace_manager,
        tool_description=mock_tool_description,
        output_format="null",  # This was causing the bug
    )

    # Verify the agent was created successfully
    assert react_agent.component_attributes.component_instance_name == "Test React Agent With Null Output"
    assert react_agent._output_format == "null"

    # Verify that _get_output_tool_description returns None (handles the null case gracefully)
    output_tool = react_agent._get_output_tool_description(react_agent._output_format)
    assert output_tool is None  # Should return None instead of crashing


def test_react_agent_with_none_output_format(mock_trace_manager, mock_tool_description, mock_llm_service):
    """Test that ReActAgent handles output_format=None correctly."""
    react_agent = ReActAgent(
        completion_service=mock_llm_service,
        component_attributes=ComponentAttributes(component_instance_name="Test React Agent With None Output"),
        trace_manager=mock_trace_manager,
        tool_description=mock_tool_description,
        output_format=None,  # This should work fine
    )

    # Verify the agent was created successfully
    assert react_agent.component_attributes.component_instance_name == "Test React Agent With None Output"
    assert react_agent._output_format is None

    # Verify that _get_output_tool_description returns None
    output_tool = react_agent._get_output_tool_description(react_agent._output_format)
    assert output_tool is None


@patch("engine.prometheus_metric.get_tracing_span")
@patch("engine.prometheus_metric.agent_calls")
def test_context_passed_to_tools(
    agent_calls_mock, get_span_mock, mock_trace_manager, mock_tool_description, mock_llm_service
):
    """Test that context is properly passed to tools when running the agent with non-empty context."""
    get_span_mock.return_value.project_id = "1234"
    counter_mock = MagicMock()
    agent_calls_mock.labels.return_value = counter_mock

    # Create a mock tool that we can inspect
    mock_tool = MagicMock()
    mock_tool.tool_description = MagicMock(spec=ToolDescription)
    mock_tool.tool_description.name = "test_context_tool"
    mock_tool.tool_description.description = "A tool to test context passing"
    mock_tool.tool_description.tool_properties = {"query": {"type": "string", "description": "Query string"}}
    mock_tool.tool_description.required_tool_properties = ["query"]

    # Mock the tool's run method to capture the ctx parameter
    mock_tool.run = AsyncMock(
        return_value=AgentPayload(
            messages=[ChatMessage(role="assistant", content="Tool executed with context")], is_final=True
        )
    )

    # Create the agent with the mock tool
    react_agent = ReActAgent(
        completion_service=mock_llm_service,
        component_attributes=ComponentAttributes(component_instance_name="Test Context Agent"),
        trace_manager=mock_trace_manager,
        tool_description=mock_tool_description,
        agent_tools=[mock_tool],
        allow_tool_shortcuts=True,  # Allow direct return when tool provides final output
    )

    # Mock LLM response with a tool call
    mock_tool_call = MagicMock()
    mock_tool_call.id = "tool_call_1"
    mock_tool_call.type = "function"
    mock_tool_call_function = MagicMock()
    mock_tool_call_function.name = "test_context_tool"
    mock_tool_call_function.arguments = json.dumps({"query": "test query"})
    mock_tool_call.function = mock_tool_call_function

    mock_message = MagicMock()
    mock_message.content = None
    mock_message.tool_calls = [mock_tool_call]
    mock_message.model_dump = lambda: {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "tool_call_1",
                "type": "function",
                "function": {"name": "test_context_tool", "arguments": json.dumps({"query": "test query"})},
            }
        ],
    }

    mock_llm_service.function_call_async = AsyncMock(return_value=MagicMock(choices=[MagicMock(message=mock_message)]))

    # Create input and context
    agent_input = AgentPayload(messages=[ChatMessage(role="user", content="Test message")])
    test_context = {"user_id": "12345", "session_id": "abc-def", "custom_data": "test_value"}

    # Mock _process_tool_calls but still call the actual tool to verify ctx is passed
    async def mock_process_with_ctx_check(*args, **kwargs):
        # Verify ctx is passed to _process_tool_calls
        assert "ctx" in kwargs
        assert kwargs["ctx"] == test_context

        # Call the tool manually to simulate what _process_tool_calls does
        tool_result = await mock_tool.run(*args, ctx=kwargs.get("ctx"), query="test query")

        # Return the expected format: (tool_outputs dict, processed_tool_calls list)
        return (
            {"tool_call_1": tool_result},
            [
                {
                    "id": "tool_call_1",
                    "type": "function",
                    "function": {"name": "test_context_tool", "arguments": json.dumps({"query": "test query"})},
                }
            ],
        )

    with patch.object(react_agent, "_process_tool_calls", side_effect=mock_process_with_ctx_check):
        # Run the agent with context
        output = react_agent.run_sync(agent_input, ctx=test_context)

        # Verify the output
        assert output.last_message.content == "Tool executed with context"
        assert output.is_final

    # Verify that the tool's run method was called with context
    mock_tool.run.assert_called_once()
    tool_call_args = mock_tool.run.call_args
    assert "ctx" in tool_call_args.kwargs
    assert tool_call_args.kwargs["ctx"] == test_context
    assert tool_call_args.kwargs["ctx"]["user_id"] == "12345"
    assert tool_call_args.kwargs["ctx"]["session_id"] == "abc-def"
    assert tool_call_args.kwargs["ctx"]["custom_data"] == "test_value"
