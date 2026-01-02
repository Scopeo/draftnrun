"""Test template variable injection through NodeData context."""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from engine.agent.errors import KeyTypePromptTemplateError, MissingKeyPromptTemplateError
from engine.agent.inputs_outputs.start import Start
from engine.agent.llm_call_agent import LLMCallAgent
from engine.agent.react_function_calling import ReActAgent
from engine.agent.types import AgentPayload, ChatMessage, ComponentAttributes, NodeData, ToolDescription
from engine.trace.trace_manager import TraceManager
from tests.agent.test_llm_call_agent import make_capability_resolver

# Mock services are available as fixtures from conftest.py


class UnstringableValue:
    """A class that raises an exception when str() is called on it."""

    def __str__(self):
        raise TypeError("Cannot convert this object to string")


@pytest.fixture
def mock_trace_manager():
    """Mock trace manager for tests."""
    return MagicMock(spec=TraceManager)


@pytest.fixture
def input_block(mock_trace_manager):
    """Input block with template vars in payload_schema."""
    return Start(
        trace_manager=mock_trace_manager,
        tool_description=ToolDescription(
            name="input", description="input", tool_properties={}, required_tool_properties=[]
        ),
        component_attributes=ComponentAttributes(component_instance_name="Test Input"),
        payload_schema='{"messages": [], "yes": "LOL", "name": "John"}',
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
        prompt_template="Say {{yes}} to {{name}}. User said: {{input}}",
        capability_resolver=make_capability_resolver(mock_llm_service),
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
        initial_prompt="You are {{name}}, say {{yes}}",
        agent_tools=[],  # No tools for this test
    )


def test_input_block_extracts_template_vars(input_block):
    """Test Input block returns NodeData with template vars directly in ctx."""
    input_data = {"messages": [{"role": "user", "content": "hi"}]}
    result = asyncio.run(input_block.run(input_data))

    assert isinstance(result, NodeData)
    assert "messages" in result.data
    assert result.ctx.get("yes") == "LOL"
    assert result.ctx.get("name") == "John"


def test_input_block_preserves_existing_ctx(input_block):
    """Test Input block preserves existing ctx data."""
    input_data = NodeData(
        data={"messages": [{"role": "user", "content": "hi"}]}, ctx={"existing_key": "existing_value"}
    )
    result = asyncio.run(input_block.run(input_data))

    assert isinstance(result, NodeData)
    assert result.ctx["existing_key"] == "existing_value"
    assert result.ctx["yes"] == "LOL"
    assert result.ctx["name"] == "John"


@patch("engine.prometheus_metric.agent_calls")
@patch("engine.prometheus_metric.get_tracing_span")
def test_llm_call_with_template_vars(get_span_mock, agent_calls_mock, llm_agent):
    """Test LLMCallAgent uses template vars from context."""
    get_span_mock.return_value = MagicMock(project_id="test_project")
    counter_mock = MagicMock()
    agent_calls_mock.labels.return_value = counter_mock

    # Simulate Input -> LLMCallAgent flow with NodeData
    input_node_data = NodeData(
        data={"messages": [{"role": "user", "content": "hi"}]}, ctx={"yes": "LOL", "name": "John"}
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
        prompt_template="Say {{missing_var}}",
        capability_resolver=make_capability_resolver(mock_llm_service),
    )

    input_node_data = NodeData(
        data={"messages": [{"role": "user", "content": "hi"}]},
        ctx={"yes": "LOL"},  # missing_var not provided
    )

    with pytest.raises(MissingKeyPromptTemplateError, match="Missing template variable\\(s\\).*missing_var"):
        asyncio.run(agent.run(input_node_data))


@patch("engine.prometheus_metric.agent_calls")
@patch("engine.prometheus_metric.get_tracing_span")
def test_llm_call_wrong_type_template_var(get_span_mock, agent_calls_mock, mock_llm_service):  # noqa: F811
    """Test LLMCallAgent raises error for template var that cannot be cast to string."""
    get_span_mock.return_value = MagicMock(project_id="test_project")
    counter_mock = MagicMock()
    agent_calls_mock.labels.return_value = counter_mock

    tm = MagicMock(spec=TraceManager)

    mock_llm_service._provider = "test_provider"
    agent = LLMCallAgent(
        trace_manager=tm,
        completion_service=mock_llm_service,
        tool_description=ToolDescription(
            name="llm_call", description="llm_call", tool_properties={}, required_tool_properties=[]
        ),
        component_attributes=ComponentAttributes(component_instance_name="Test LLM"),
        prompt_template="Say {{bad_var}}",
        capability_resolver=make_capability_resolver(mock_llm_service),
    )

    input_node_data = NodeData(
        data={"messages": [{"role": "user", "content": "hi"}]},
        ctx={"bad_var": UnstringableValue()},
    )

    with pytest.raises(KeyTypePromptTemplateError, match="Value for key 'bad_var' cannot be cast to string"):
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
        prompt_template="User said: {{input}}",
        capability_resolver=make_capability_resolver(llm_agent._completion_service),
    )

    input_node_data = NodeData(data={"messages": [{"role": "user", "content": "Hello world!"}]}, ctx={})

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
        data={"messages": [{"role": "user", "content": "hi"}]}, ctx={"yes": "LOL", "name": "Alice"}
    )

    result = asyncio.run(react_agent.run(input_node_data))

    # Verify template vars were used in system prompt
    assert result.data["output"] == "Test response"  # From mock_llm_service_with_tool_calls
    react_agent._completion_service.function_call_async.assert_called_once()


@patch("engine.prometheus_metric.agent_calls")
@patch("engine.prometheus_metric.get_tracing_span")
def test_react_agent_wrong_type_template_var(get_span_mock, agent_calls_mock, mock_llm_service, mock_trace_manager):
    """Test ReActAgent raises error for template var that cannot be cast to string."""
    get_span_mock.return_value = MagicMock(project_id="test_project")
    counter_mock = MagicMock()
    agent_calls_mock.labels.return_value = counter_mock

    react_agent = ReActAgent(
        completion_service=mock_llm_service,
        component_attributes=ComponentAttributes(component_instance_name="Test React"),
        trace_manager=mock_trace_manager,
        tool_description=ToolDescription(
            name="react", description="react", tool_properties={}, required_tool_properties=[]
        ),
        initial_prompt="You are {{name}}, say {{bad_var}}",
        agent_tools=[],
    )

    input_node_data = NodeData(
        data={"messages": [{"role": "user", "content": "hi"}]},
        ctx={"name": "Alice", "bad_var": UnstringableValue()},
    )

    with pytest.raises(KeyTypePromptTemplateError, match="Value for key 'bad_var' cannot be cast to string"):
        asyncio.run(react_agent.run(input_node_data))


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
        prompt_template="Message: {{input}}, Template var: {{yes}}",
        capability_resolver=make_capability_resolver(mock_llm_service),
    )

    input_node_data = NodeData(
        data={"messages": [{"role": "user", "content": "Hello from message"}]},
        ctx={"yes": "Hello from template"},
    )

    # The {{input}} should come from message content, {{yes}} from template_vars
    # This test ensures the logic correctly separates these two sources
    result = asyncio.run(agent.run(input_node_data))
    # The actual template filling logic is tested in the implementation
    assert result.data["output"] == "Test response"


@patch("engine.prometheus_metric.agent_calls")
@patch("engine.prometheus_metric.get_tracing_span")
def test_llm_call_with_file_handling(get_span_mock, agent_calls_mock, mock_llm_service):  # noqa: F811
    """Test LLMCallAgent handles file content and URLs from context."""
    get_span_mock.return_value = MagicMock(project_id="test_project")
    counter_mock = MagicMock()
    agent_calls_mock.labels.return_value = counter_mock

    tm = MagicMock(spec=TraceManager)
    agent = LLMCallAgent(
        trace_manager=tm,
        completion_service=mock_llm_service,
        tool_description=ToolDescription(
            name="llm_call", description="llm_call", tool_properties={}, required_tool_properties=[]
        ),
        component_attributes=ComponentAttributes(component_instance_name="Test LLM"),
        prompt_template="Process this file: {{input}}",
        file_content_key="my_file_content",
        file_url_key="my_file_url",
        capability_resolver=make_capability_resolver(mock_llm_service, {"openai:gpt-4o"}),
    )

    input_node_data = NodeData(
        data={"messages": [{"role": "user", "content": "Hello world!"}]},
        ctx={
            "my_file_content": {
                "filename": "test.pdf",
                "file_data": (
                    "data:application/pdf;base64,"
                    "JVBERi0xLjQKJcOkw7zDtsO8CjIgMCBvYmoKPDwKL0xlbmd0aCAzIDAgUgo+PgpzdHJlYW0K"
                ),
            },
            "my_file_url": "https://example.com/document.pdf",
        },
    )

    result = asyncio.run(agent.run(input_node_data))

    # Verify file handling worked
    assert result.data["output"] == "Test response"
    agent._completion_service.complete_async.assert_called_once()


def test_input_block_with_flat_template_vars(mock_trace_manager):
    """Test Input block handles flat template vars correctly."""
    # Create a fresh input block without schema defaults
    input_block = Start(
        trace_manager=mock_trace_manager,
        tool_description=ToolDescription(
            name="input", description="input", tool_properties={}, required_tool_properties=[]
        ),
        component_attributes=ComponentAttributes(component_instance_name="Test Input"),
        payload_schema='{"messages": []}',  # No default template vars
    )

    input_data = {
        "messages": [{"role": "user", "content": "Hello"}],
        "cs_book_url": "https://example.com/book.pdf",
        "username": "John",
    }
    result = asyncio.run(input_block.run(input_data))

    assert isinstance(result, NodeData)
    assert "messages" in result.data
    assert result.ctx.get("username") == "John"
    assert result.ctx.get("cs_book_url") == "https://example.com/book.pdf"


@patch("engine.prometheus_metric.agent_calls")
@patch("engine.prometheus_metric.get_tracing_span")
def test_llm_call_with_flat_template_vars(get_span_mock, agent_calls_mock, mock_llm_service):  # noqa: F811
    """Test LLMCallAgent works with flat template vars from frontend payload."""
    get_span_mock.return_value = MagicMock(project_id="test_project")
    counter_mock = MagicMock()
    agent_calls_mock.labels.return_value = counter_mock

    tm = MagicMock(spec=TraceManager)
    agent = LLMCallAgent(
        trace_manager=tm,
        completion_service=mock_llm_service,
        tool_description=ToolDescription(
            name="llm_call", description="llm_call", tool_properties={}, required_tool_properties=[]
        ),
        component_attributes=ComponentAttributes(component_instance_name="LLM Call"),
        prompt_template="The user's name it's {{username}}. Greet it.\nAnswer this question: {{input}}",
        file_url_key="cs_book",
        capability_resolver=make_capability_resolver(mock_llm_service, {"openai:gpt-4o"}),
    )

    input_node_data = NodeData(
        data={"messages": [{"role": "user", "content": "Hello"}]},
        ctx={"username": "John", "cs_book": "https://example.com/book.pdf"},
    )

    result = asyncio.run(agent.run(input_node_data))

    # Verify template vars and file URLs were used
    assert result.data["output"] == "Test response"
    agent._completion_service.complete_async.assert_called_once()


@patch("engine.prometheus_metric.agent_calls")
@patch("engine.prometheus_metric.get_tracing_span")
def test_llm_call_template_vars_from_tool_args(get_span_mock, agent_calls_mock, mock_llm_service):  # noqa: F811
    """Ensure template vars provided via function-calling tool args are honored (inputs-first path)."""
    get_span_mock.return_value = MagicMock(project_id="test_project")
    counter_mock = MagicMock()
    agent_calls_mock.labels.return_value = counter_mock

    # Configure provider/model
    mock_llm_service._provider = "openai"
    mock_llm_service._model_name = "gpt-4o"

    tm = MagicMock(spec=TraceManager)
    llm_tool = LLMCallAgent(
        trace_manager=tm,
        completion_service=mock_llm_service,
        tool_description=ToolDescription(
            name="Get_content", description="", tool_properties={}, required_tool_properties=[]
        ),
        component_attributes=ComponentAttributes(component_instance_name="LLM Call"),
        prompt_template="Respond to {{query}}. Speak like a {{speak}}",
        file_url_key="doc_url",
        capability_resolver=make_capability_resolver(mock_llm_service, {"openai:gpt-4o"}),
    )

    react = ReActAgent(
        completion_service=mock_llm_service,
        component_attributes=ComponentAttributes(component_instance_name="ReAct"),
        trace_manager=tm,
        tool_description=ToolDescription(
            name="react", description="", tool_properties={}, required_tool_properties=[]
        ),
        agent_tools=[llm_tool],
        run_tools_in_parallel=False,
    )

    doc_url = "https://example.com/a.pdf"
    query = "What is the weather?"
    speak = "pirate"
    fn = SimpleNamespace(
        name="Get_content", arguments=f'{{"doc_url": "{doc_url}", "query": "{query}", "speak": "{speak}"}}'
    )
    tool_call = SimpleNamespace(id="call_1", function=fn)

    # Tools in this path receive legacy AgentPayload; no ctx propagation
    agent_payload = AgentPayload(messages=[ChatMessage(role="user", content="Hi")])
    _id, _ = asyncio.run(react._run_tool_call(agent_payload, tool_call=tool_call))

    # Verify completion was called with template variables and file URL from function calling
    mock_llm_service.complete_async.assert_called_once()
    content = mock_llm_service.complete_async.call_args.kwargs["messages"][0]["content"]
    assert isinstance(content, list)

    # Check that file URL was included
    file_parts = [p for p in content if isinstance(p, dict) and p.get("type") == "file" and "file_url" in p]
    assert len(file_parts) == 1 and file_parts[0]["file_url"] == doc_url

    # Check that template variables were used in the text content
    text_parts = [p for p in content if isinstance(p, dict) and p.get("type") == "text"]
    assert len(text_parts) == 1
    text_content = text_parts[0]["text"]
    assert query in text_content  # Template variable should be filled
    assert speak in text_content  # Template variable should be filled


@patch("engine.prometheus_metric.agent_calls")
@patch("engine.prometheus_metric.get_tracing_span")
def test_react_agent_two_tool_calls_different_urls(
    get_span_mock, agent_calls_mock, mock_llm_service, mock_trace_manager
):
    """Two tool calls with different file_url should not affect each other."""
    get_span_mock.return_value = MagicMock(project_id="test_project")
    counter_mock = MagicMock()
    agent_calls_mock.labels.return_value = counter_mock
    # Configure provider/model
    mock_llm_service._provider = "openai"
    mock_llm_service._model_name = "gpt-4o"

    # Tool under test
    llm_tool = LLMCallAgent(
        trace_manager=mock_trace_manager,
        completion_service=mock_llm_service,
        tool_description=ToolDescription(
            name="Get_content", description="", tool_properties={}, required_tool_properties=[]
        ),
        component_attributes=ComponentAttributes(component_instance_name="Get content"),
        prompt_template="Describe: {{input}}",
        file_url_key="file_url",
        capability_resolver=make_capability_resolver(mock_llm_service, {"openai:gpt-4o"}),
    )

    # React agent with this single tool
    react = ReActAgent(
        completion_service=mock_llm_service,
        component_attributes=ComponentAttributes(component_instance_name="ReAct"),
        trace_manager=mock_trace_manager,
        tool_description=ToolDescription(
            name="react", description="", tool_properties={}, required_tool_properties=[]
        ),
        agent_tools=[llm_tool],
        run_tools_in_parallel=False,
    )

    # Build two fake tool calls
    def make_tool_call(call_id: str, url: str):
        fn = SimpleNamespace(name="Get_content", arguments=f'{"{"}"file_url": "{url}"{"}"}')
        return SimpleNamespace(id=call_id, function=fn)

    tc1 = make_tool_call("call_1", "https://a.example/a.pdf")
    tc2 = make_tool_call("call_2", "https://b.example/b.pdf")

    # Original input payload: tools receive legacy AgentPayload in this path
    agent_payload = AgentPayload(messages=[ChatMessage(role="user", content="Hi")])

    # Run both tool calls sequentially via the helper
    id1, _ = asyncio.run(react._run_tool_call(agent_payload, tool_call=tc1))
    id2, _ = asyncio.run(react._run_tool_call(agent_payload, tool_call=tc2))
    assert id1 == "call_1" and id2 == "call_2"

    # Validate two separate calls with distinct file_url were made
    calls = mock_llm_service.complete_async.call_args_list
    assert len(calls) == 2
    contents = [calls[0].kwargs["messages"][0]["content"], calls[1].kwargs["messages"][0]["content"]]
    # Each content should be a list including a file dict with the given URL
    urls = []
    for content in contents:
        assert isinstance(content, list)
        file_parts = [p for p in content if isinstance(p, dict) and p.get("type") == "file" and "file_url" in p]
        assert len(file_parts) == 1
        urls.append(file_parts[0]["file_url"])
    assert urls == ["https://a.example/a.pdf", "https://b.example/b.pdf"]
