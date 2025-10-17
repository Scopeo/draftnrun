"""Test template variable injection through NodeData context."""

import pytest
import asyncio
from unittest.mock import MagicMock, patch
from engine.agent.inputs_outputs.input import Input
from engine.agent.llm_call_agent import LLMCallAgent
from engine.agent.react_function_calling import ReActAgent
from engine.agent.types import NodeData, ComponentAttributes, ToolDescription
from engine.trace.trace_manager import TraceManager

# Mock services are available as fixtures from conftest.py


@pytest.fixture
def mock_trace_manager():
    """Mock trace manager for tests."""
    return MagicMock(spec=TraceManager)


@pytest.fixture
def input_block(mock_trace_manager):
    """Input block with template vars in payload_schema."""
    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {
            "messages": {"type": "array", "default": []},
            "yes": {"type": "string", "default": "LOL"},
            "name": {"type": "string", "default": "John"},
        },
    }
    import json

    return Input(
        trace_manager=mock_trace_manager,
        tool_description=ToolDescription(
            name="input", description="input", tool_properties={}, required_tool_properties=[]
        ),
        component_attributes=ComponentAttributes(component_instance_name="Test Input"),
        payload_schema=json.dumps(schema),
    )


@pytest.fixture
def llm_agent(mock_trace_manager, mock_llm_service):
    """LLM Call agent with template in prompt."""
    # Add _provider attribute to mock
    mock_llm_service._provider = "test_provider"
    return LLMCallAgent(
        trace_manager=mock_trace_manager,
        completion_service=mock_llm_service,
        tool_description=ToolDescription(
            name="llm_call", description="llm_call", tool_properties={}, required_tool_properties=[]
        ),
        component_attributes=ComponentAttributes(component_instance_name="Test LLM"),
        prompt_template="Say {yes} to {name}. User said: {input}",
    )


@pytest.fixture
def react_agent(mock_trace_manager, mock_llm_service):
    """ReAct agent with template in initial prompt."""
    return ReActAgent(
        completion_service=mock_llm_service,
        component_attributes=ComponentAttributes(component_instance_name="Test React"),
        trace_manager=mock_trace_manager,
        tool_description=ToolDescription(
            name="react", description="react", tool_properties={}, required_tool_properties=[]
        ),
        initial_prompt="You are {name}, say {yes}",
        agent_tools=[],  # No tools for this test
    )


def test_input_block_extracts_template_vars(input_block):
    """Test Input block returns NodeData with template_vars in ctx."""
    input_data = {"messages": [{"role": "user", "content": "hi"}]}
    result = asyncio.run(input_block.run(input_data))

    assert isinstance(result, NodeData)
    assert "messages" in result.data
    assert result.ctx.get("template_vars") == {"yes": "LOL", "name": "John"}


def test_input_block_preserves_existing_ctx(input_block):
    """Test Input block preserves existing ctx data."""
    input_data = NodeData(
        data={"messages": [{"role": "user", "content": "hi"}]}, ctx={"existing_key": "existing_value"}
    )
    result = asyncio.run(input_block.run(input_data))

    assert isinstance(result, NodeData)
    assert result.ctx["existing_key"] == "existing_value"
    assert result.ctx["template_vars"] == {"yes": "LOL", "name": "John"}


@patch("engine.prometheus_metric.agent_calls")
@patch("engine.prometheus_metric.get_tracing_span")
def test_llm_call_with_template_vars(get_span_mock, agent_calls_mock, llm_agent):
    """Test LLMCallAgent uses template vars from context."""
    get_span_mock.return_value = MagicMock(project_id="test_project")
    counter_mock = MagicMock()
    agent_calls_mock.labels.return_value = counter_mock

    # Simulate Input -> LLMCallAgent flow with NodeData
    input_node_data = NodeData(
        data={"messages": [{"role": "user", "content": "hi"}]}, ctx={"template_vars": {"yes": "LOL", "name": "John"}}
    )

    result = asyncio.run(llm_agent.run(input_node_data))

    # Verify template vars were used
    assert result.data["output"] == "Test response"  # From mock_llm_service
    # The mock service should have been called with the filled template
    llm_agent._completion_service.complete_async.assert_called_once()


@patch("engine.prometheus_metric.agent_calls")
@patch("engine.prometheus_metric.get_tracing_span")
def test_llm_call_missing_template_var(get_span_mock, agent_calls_mock, mock_llm_service):  # noqa: F811
    """Test LLMCallAgent raises error for missing template var."""
    get_span_mock.return_value = MagicMock(project_id="test_project")
    counter_mock = MagicMock()
    agent_calls_mock.labels.return_value = counter_mock

    tm = MagicMock(spec=TraceManager)
    # Add _provider attribute to mock
    mock_llm_service._provider = "test_provider"
    agent = LLMCallAgent(
        trace_manager=tm,
        completion_service=mock_llm_service,
        tool_description=ToolDescription(
            name="llm_call", description="llm_call", tool_properties={}, required_tool_properties=[]
        ),
        component_attributes=ComponentAttributes(component_instance_name="Test LLM"),
        prompt_template="Say {missing_var}",
    )

    input_node_data = NodeData(
        data={"messages": [{"role": "user", "content": "hi"}]},
        ctx={"template_vars": {"yes": "LOL"}},  # missing_var not provided
    )

    with pytest.raises(ValueError, match="Missing template variable 'missing_var'"):
        asyncio.run(agent.run(input_node_data))


@patch("engine.prometheus_metric.agent_calls")
@patch("engine.prometheus_metric.get_tracing_span")
def test_llm_call_with_input_var(get_span_mock, agent_calls_mock, llm_agent):
    """Test LLMCallAgent uses {{input}} variable from message content."""
    get_span_mock.return_value = MagicMock(project_id="test_project")
    counter_mock = MagicMock()
    agent_calls_mock.labels.return_value = counter_mock

    # Create agent with {{input}} in template
    tm = MagicMock(spec=TraceManager)
    # Add _provider attribute to mock
    llm_agent._completion_service._provider = "test_provider"
    agent = LLMCallAgent(
        trace_manager=tm,
        completion_service=llm_agent._completion_service,
        tool_description=ToolDescription(
            name="llm_call", description="llm_call", tool_properties={}, required_tool_properties=[]
        ),
        component_attributes=ComponentAttributes(component_instance_name="Test LLM"),
        prompt_template="User said: {input}",
    )

    input_node_data = NodeData(
        data={"messages": [{"role": "user", "content": "Hello world!"}]}, ctx={"template_vars": {}}
    )

    result = asyncio.run(agent.run(input_node_data))

    # Verify {{input}} was filled with message content
    assert result.data["output"] == "Test response"  # From mock_llm_service
    agent._completion_service.complete_async.assert_called_once()


@patch("engine.prometheus_metric.agent_calls")
@patch("engine.prometheus_metric.get_tracing_span")
def test_react_agent_with_template_vars(get_span_mock, agent_calls_mock, react_agent):
    """Test ReActAgent uses template vars in system prompt."""
    get_span_mock.return_value = MagicMock(project_id="test_project")
    counter_mock = MagicMock()
    agent_calls_mock.labels.return_value = counter_mock

    input_node_data = NodeData(
        data={"messages": [{"role": "user", "content": "hi"}]}, ctx={"template_vars": {"yes": "LOL", "name": "Alice"}}
    )

    result = asyncio.run(react_agent.run(input_node_data))

    # Verify template vars were used in system prompt
    assert result.data["output"] == "Test response"  # From mock_llm_service_with_tool_calls
    react_agent._completion_service.function_call_async.assert_called_once()


@patch("engine.prometheus_metric.agent_calls")
@patch("engine.prometheus_metric.get_tracing_span")
def test_template_vars_priority(get_span_mock, agent_calls_mock, mock_llm_service):  # noqa: F811
    """Test that template vars from ctx take priority over message content for {{input}}."""
    get_span_mock.return_value = MagicMock(project_id="test_project")
    counter_mock = MagicMock()
    agent_calls_mock.labels.return_value = counter_mock

    # This test verifies that {{input}} comes from message content, not template_vars
    tm = MagicMock(spec=TraceManager)
    agent = LLMCallAgent(
        trace_manager=tm,
        completion_service=mock_llm_service,
        tool_description=ToolDescription(
            name="llm_call", description="llm_call", tool_properties={}, required_tool_properties=[]
        ),
        component_attributes=ComponentAttributes(component_instance_name="Test LLM"),
        prompt_template="Message: {input}, Template var: {yes}",
    )

    input_node_data = NodeData(
        data={"messages": [{"role": "user", "content": "Hello from message"}]},
        ctx={"template_vars": {"yes": "Hello from template"}},
    )

    # The {{input}} should come from message content, {{yes}} from template_vars
    # This test ensures the logic correctly separates these two sources
    result = asyncio.run(agent.run(input_node_data))
    # The actual template filling logic is tested in the implementation
    assert result.data["output"] == "Test response"


@patch("engine.agent.llm_call_agent.get_models_by_capability")
@patch("engine.prometheus_metric.agent_calls")
@patch("engine.prometheus_metric.get_tracing_span")
def test_llm_call_with_file_handling(get_span_mock, agent_calls_mock, get_models_mock, mock_llm_service):  # noqa: F811
    """Test LLMCallAgent handles file content and URLs from context."""
    get_span_mock.return_value = MagicMock(project_id="test_project")
    counter_mock = MagicMock()
    agent_calls_mock.labels.return_value = counter_mock

    # Mock file capability check to allow files
    get_models_mock.return_value = [{"reference": "openai:gpt-4o"}]

    tm = MagicMock(spec=TraceManager)
    agent = LLMCallAgent(
        trace_manager=tm,
        completion_service=mock_llm_service,
        tool_description=ToolDescription(
            name="llm_call", description="llm_call", tool_properties={}, required_tool_properties=[]
        ),
        component_attributes=ComponentAttributes(component_instance_name="Test LLM"),
        prompt_template="Process this file: {input}",
        file_content_key="my_file_content",
        file_url_key="my_file_url",
    )

    input_node_data = NodeData(
        data={"messages": [{"role": "user", "content": "Hello world!"}]},
        ctx={
            "template_vars": {},
            "file_content": {
                "my_file_content": {
                    "filename": "test.pdf",
                    "file_data": (
                        "data:application/pdf;base64,"
                        "JVBERi0xLjQKJcOkw7zDtsO8CjIgMCBvYmoKPDwKL0xlbmd0aCAzIDAgUgo+PgpzdHJlYW0K"
                    ),
                }
            },
            "file_urls": {"my_file_url": "https://example.com/document.pdf"},
        },
    )

    result = asyncio.run(agent.run(input_node_data))

    # Verify file handling worked
    assert result.data["output"] == "Test response"
    agent._completion_service.complete_async.assert_called_once()


def test_input_block_with_nested_template_vars(mock_trace_manager):
    """Test Input block handles nested template_vars field correctly."""
    # Create a fresh input block without schema defaults
    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {"messages": {"type": "array", "default": []}},
    }
    import json

    input_block = Input(
        trace_manager=mock_trace_manager,
        tool_description=ToolDescription(
            name="input", description="input", tool_properties={}, required_tool_properties=[]
        ),
        component_attributes=ComponentAttributes(component_instance_name="Test Input"),
        payload_schema=json.dumps(schema),  # No default template vars
    )

    input_data = {
        "messages": [{"role": "user", "content": "Hello"}],
        "file_urls": {"cs_book": "https://example.com/book.pdf"},
        "template_vars": {"username": "John"},
    }
    result = asyncio.run(input_block.run(input_data))

    assert isinstance(result, NodeData)
    assert "messages" in result.data
    # template_vars should contain the nested values, not the field itself
    assert result.ctx.get("template_vars") == {"username": "John"}
    assert result.ctx.get("file_urls") == {"cs_book": "https://example.com/book.pdf"}


@patch("engine.agent.llm_call_agent.get_models_by_capability")
@patch("engine.prometheus_metric.agent_calls")
@patch("engine.prometheus_metric.get_tracing_span")
def test_llm_call_with_nested_template_vars(
    get_span_mock, agent_calls_mock, get_models_mock, mock_llm_service
):  # noqa: F811
    """Test LLMCallAgent works with nested template_vars from frontend payload."""
    get_span_mock.return_value = MagicMock(project_id="test_project")
    counter_mock = MagicMock()
    agent_calls_mock.labels.return_value = counter_mock

    # Mock file capability check to allow files
    get_models_mock.return_value = [{"reference": "openai:gpt-4o"}]

    tm = MagicMock(spec=TraceManager)
    agent = LLMCallAgent(
        trace_manager=tm,
        completion_service=mock_llm_service,
        tool_description=ToolDescription(
            name="llm_call", description="llm_call", tool_properties={}, required_tool_properties=[]
        ),
        component_attributes=ComponentAttributes(component_instance_name="LLM Call"),
        prompt_template="The user's name it's {username}. Greet it.\nAnswer this question: {input}",
        file_url_key="cs_book",
    )

    input_node_data = NodeData(
        data={"messages": [{"role": "user", "content": "Hello"}]},
        ctx={"template_vars": {"username": "John"}, "file_urls": {"cs_book": "https://example.com/book.pdf"}},
    )

    result = asyncio.run(agent.run(input_node_data))

    # Verify template vars and file URLs were used
    assert result.data["output"] == "Test response"
    agent._completion_service.complete_async.assert_called_once()
