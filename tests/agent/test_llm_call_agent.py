import asyncio
import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from engine.agent.agent import ComponentAttributes
from engine.agent.llm_call_agent import LLMCallAgent, LLMCallInputs
from engine.agent.react_function_calling import ReActAgent
from engine.agent.types import NodeData, ToolDescription, AgentPayload, ChatMessage
from engine.trace.trace_manager import TraceManager


def make_capability_resolver(service, default_capabilities=None):
    def resolver(capabilities):
        provider = getattr(service, "_provider", None)
        model = getattr(service, "_model_name", None)
        refs = set(default_capabilities) if default_capabilities else set()
        if provider and model:
            refs.add(f"{provider}:{model}")
        return refs

    return resolver


FILE_PATH_1 = "file_1.pdf"
FILE_PATH_2 = "file_2.pdf"
QUESTION = "What is the content of the file?"
base64_string = base64.b64encode(b"dummy pdf content").decode("utf-8")


@pytest.fixture
def input_payload_format_file_as_message():
    return {
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "file",
                        "file": {
                            "filename": FILE_PATH_1,
                            "file_data": f"data:application/pdf;base64,{base64_string}",
                        },
                    },
                    {
                        "type": "text",
                        "text": QUESTION,
                    },
                ],
            },
        ],
    }


@pytest.fixture
def input_payload_format_file_as_independant_key():
    return {
        "messages": [
            {
                "role": "user",
                "content": QUESTION,
            },
        ],
        "file": {
            "filename": FILE_PATH_1,
            "file_data": f"data:application/pdf;base64,{base64_string}",
        },
    }


@pytest.fixture
def input_payload_format_file_as_both_message_and_independant_key():
    return {
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "file",
                        "file": {
                            "filename": FILE_PATH_1,
                            "file_data": f"data:application/pdf;base64,{base64_string}",
                        },
                    },
                    {
                        "type": "text",
                        "text": QUESTION,
                    },
                ],
            },
        ],
        "file": {
            "filename": FILE_PATH_2,
            "file_data": f"data:application/pdf;base64,{base64_string}",
        },
    }


@pytest.fixture
def input_payload_format_no_file():
    return {
        "messages": [
            {
                "role": "user",
                "content": QUESTION,
            },
        ],
    }


async def complete_side_effect(**kwargs):
    content = kwargs["messages"][0]["content"]
    # If content is a list (with files), extract the text part
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                return item["text"]
        return "What is the content of the file?"  # fallback
    return content


@pytest.fixture
def llm_call_with_file_content():
    trace_manager = MagicMock()
    llm_service = MagicMock()
    llm_service._provider = "openai"  # Set the provider to openai to support file content
    llm_service._model_name = "gpt-4.1-mini"  # Set a model that supports files

    # Use AsyncMock for the async methods
    llm_service.complete_async = AsyncMock(side_effect=complete_side_effect)
    llm_service.constrained_complete_with_json_schema_async = AsyncMock(side_effect=complete_side_effect)

    tool_description = MagicMock()
    component_attributes = ComponentAttributes(
        component_instance_name="test_component",
    )
    prompt_template = "{input}"
    file_content = "{file}"
    return LLMCallAgent(
        trace_manager,
        llm_service,
        tool_description,
        component_attributes,
        prompt_template,
        file_content_key=file_content,
        capability_resolver=make_capability_resolver(llm_service),
    )


@pytest.fixture
def llm_call_without_file_content():
    trace_manager = MagicMock()
    llm_service = MagicMock()
    llm_service._provider = "openai"  # Set the provider to openai to support file content
    llm_service._model_name = "gpt-4.1-mini"  # Set a model that supports files

    # Use AsyncMock for the async methods
    llm_service.complete_async = AsyncMock(side_effect=complete_side_effect)
    llm_service.constrained_complete_with_json_schema_async = AsyncMock(side_effect=complete_side_effect)

    tool_description = MagicMock()
    component_attributes = ComponentAttributes(component_instance_name="test_component")
    prompt_template = "{input}"
    return LLMCallAgent(
        trace_manager,
        llm_service,
        tool_description,
        component_attributes,
        prompt_template,
        capability_resolver=make_capability_resolver(llm_service),
    )


@pytest.mark.parametrize(
    "agent,input_payload,expected_file",
    [
        ("llm_call_with_file_content", "input_payload_format_no_file", None),
        ("llm_call_with_file_content", "input_payload_format_file_as_message", FILE_PATH_1),
        ("llm_call_with_file_content", "input_payload_format_file_as_independant_key", FILE_PATH_1),
        ("llm_call_with_file_content", "input_payload_format_file_as_both_message_and_independant_key", FILE_PATH_1),
        ("llm_call_without_file_content", "input_payload_format_no_file", None),
        ("llm_call_without_file_content", "input_payload_format_file_as_message", FILE_PATH_1),
        ("llm_call_without_file_content", "input_payload_format_file_as_independant_key", FILE_PATH_1),
        (
            "llm_call_without_file_content",
            "input_payload_format_file_as_both_message_and_independant_key",
            FILE_PATH_1,
        ),
    ],
)
def test_agent_input_combinations(agent, input_payload, expected_file, request):
    agent_instance = request.getfixturevalue(agent)
    payload_instance = request.getfixturevalue(input_payload)

    # Convert dict to LLMCallInputs Pydantic model
    inputs = LLMCallInputs.model_validate(payload_instance)

    response = asyncio.run(agent_instance._run_without_io_trace(inputs, ctx={}))

    # Check that the response contains the expected output
    assert isinstance(response.output, str)
    assert QUESTION in response.output


@patch("engine.prometheus_metric.agent_calls")
@patch("engine.prometheus_metric.get_tracing_span")
def test_file_url_from_api_input(get_span_mock, agent_calls_mock):
    """Test file_url from API input (NodeData.data) for block LLM Call."""
    get_span_mock.return_value = MagicMock(project_id="test_project")
    counter_mock = MagicMock()
    agent_calls_mock.labels.return_value = counter_mock

    trace_manager = MagicMock(spec=TraceManager)
    llm_service = MagicMock()
    llm_service._provider = "openai"
    llm_service._model_name = "gpt-4o"
    llm_service.complete_async = AsyncMock(return_value="Test response")

    agent = LLMCallAgent(
        trace_manager=trace_manager,
        completion_service=llm_service,
        tool_description=ToolDescription(
            name="llm_call", description="llm_call", tool_properties={}, required_tool_properties=[]
        ),
        component_attributes=ComponentAttributes(component_instance_name="LLM Call"),
        prompt_template="Process this file: {input}",
        file_url_key="document_url",
        capability_resolver=make_capability_resolver(llm_service, {"openai:gpt-4o"}),
    )

    # file_url passed directly in NodeData.data (API input), not in ctx
    file_url = "https://example.com/document.pdf"
    input_node_data = NodeData(
        data={
            "messages": [{"role": "user", "content": "Analyze this document"}],
            "document_url": file_url,  # file_url in data, not ctx
        },
        ctx={},  # Empty ctx to ensure file_url comes from data
    )

    result = asyncio.run(agent.run(input_node_data))

    # Verify file URL was extracted and used
    assert result.data["output"] == "Test response"
    llm_service.complete_async.assert_called_once()
    content = llm_service.complete_async.call_args.kwargs["messages"][0]["content"]
    assert isinstance(content, list)

    # Check that file URL was included in the content
    file_parts = [p for p in content if isinstance(p, dict) and p.get("type") == "file" and "file_url" in p]
    assert len(file_parts) == 1
    assert file_parts[0]["file_url"] == file_url


@patch("engine.prometheus_metric.agent_calls")
@patch("engine.prometheus_metric.get_tracing_span")
def test_template_vars_from_api_input(get_span_mock, agent_calls_mock):
    """Test template_vars from API input (NodeData.data) for block LLM Call."""
    get_span_mock.return_value = MagicMock(project_id="test_project")
    counter_mock = MagicMock()
    agent_calls_mock.labels.return_value = counter_mock

    trace_manager = MagicMock(spec=TraceManager)
    llm_service = MagicMock()
    llm_service._provider = "openai"
    llm_service._model_name = "gpt-4o"
    llm_service.complete_async = AsyncMock(return_value="Test response")

    agent = LLMCallAgent(
        trace_manager=trace_manager,
        completion_service=llm_service,
        tool_description=ToolDescription(
            name="llm_call", description="llm_call", tool_properties={}, required_tool_properties=[]
        ),
        component_attributes=ComponentAttributes(component_instance_name="LLM Call"),
        prompt_template="Hello {username}, answer this: {input}. Use style: {style}",
        capability_resolver=make_capability_resolver(llm_service, {"openai:gpt-4o"}),
    )

    # template_vars passed directly in NodeData.data (API input), not in ctx
    input_node_data = NodeData(
        data={
            "messages": [{"role": "user", "content": "What is AI?"}],
            "username": "Alice",  # template var in data
            "style": "formal",  # template var in data
        },
        ctx={},  # Empty ctx to ensure template vars come from data
    )

    result = asyncio.run(agent.run(input_node_data))

    # Verify template vars were used
    assert result.data["output"] == "Test response"
    llm_service.complete_async.assert_called_once()
    content = llm_service.complete_async.call_args.kwargs["messages"][0]["content"]

    # Check that template variables were filled in the text content
    # Content can be a string or a list (if files are included)
    if isinstance(content, list):
        text_parts = [p for p in content if isinstance(p, dict) and p.get("type") == "text"]
        assert len(text_parts) == 1
        text_content = text_parts[0]["text"]
    else:
        text_content = content

    # Verify template variables were filled
    assert "Alice" in text_content, f"Expected 'Alice' in content: {text_content}"
    assert "formal" in text_content, f"Expected 'formal' in content: {text_content}"
    assert "What is AI?" in text_content, f"Expected input message in content: {text_content}"


@patch("engine.prometheus_metric.agent_calls")
@patch("engine.prometheus_metric.get_tracing_span")
def test_file_url_as_tool_property(get_span_mock, agent_calls_mock):
    """Test file_url input as tool (tool properties) for LLM Call."""
    get_span_mock.return_value = MagicMock(project_id="test_project")
    counter_mock = MagicMock()
    agent_calls_mock.labels.return_value = counter_mock

    trace_manager = MagicMock(spec=TraceManager)
    llm_service = MagicMock()
    llm_service._provider = "openai"
    llm_service._model_name = "gpt-4o"
    llm_service.complete_async = AsyncMock(return_value="Test response")

    # Create LLM Call agent with file_url_key and tool_properties that include file_url
    llm_tool = LLMCallAgent(
        trace_manager=trace_manager,
        completion_service=llm_service,
        tool_description=ToolDescription(
            name="AnalyzeDocument",
            description="Analyze a document from a URL",
            tool_properties={
                "document_url": {
                    "type": "string",
                    "description": "URL to the document to analyze",
                },
            },
            required_tool_properties=["document_url"],
        ),
        component_attributes=ComponentAttributes(component_instance_name="Analyze Document"),
        prompt_template="Analyze this document.",
        file_url_key="document_url",
        capability_resolver=make_capability_resolver(llm_service, {"openai:gpt-4o"}),
    )

    # Create ReAct agent with the LLM tool
    react = ReActAgent(
        completion_service=llm_service,
        component_attributes=ComponentAttributes(component_instance_name="ReAct"),
        trace_manager=trace_manager,
        tool_description=ToolDescription(
            name="react", description="", tool_properties={}, required_tool_properties=[]
        ),
        agent_tools=[llm_tool],
        run_tools_in_parallel=False,
    )

    # Simulate tool call with file_url as tool property
    document_url = "https://example.com/report.pdf"
    fn = SimpleNamespace(
        name="AnalyzeDocument",
        arguments=f'{{"messages": [], "document_url": "{document_url}"}}',
    )
    tool_call = SimpleNamespace(id="call_1", function=fn)

    # Tools receive legacy AgentPayload in this path
    agent_payload = AgentPayload(messages=[ChatMessage(role="user", content="Analyze the document")])
    _id, _ = asyncio.run(react._run_tool_call(agent_payload, tool_call=tool_call))

    # Verify completion was called with file URL from tool properties
    llm_service.complete_async.assert_called_once()
    content = llm_service.complete_async.call_args.kwargs["messages"][0]["content"]
    assert isinstance(content, list)

    # Check that file URL was included
    file_parts = [p for p in content if isinstance(p, dict) and p.get("type") == "file" and "file_url" in p]
    assert len(file_parts) == 1
    assert file_parts[0]["file_url"] == document_url


@patch("engine.prometheus_metric.agent_calls")
@patch("engine.prometheus_metric.get_tracing_span")
def test_template_vars_as_tool_property(get_span_mock, agent_calls_mock):
    """Test template_vars as tool (tool properties) for LLM Call."""
    get_span_mock.return_value = MagicMock(project_id="test_project")
    counter_mock = MagicMock()
    agent_calls_mock.labels.return_value = counter_mock

    trace_manager = MagicMock(spec=TraceManager)
    llm_service = MagicMock()
    llm_service._provider = "openai"
    llm_service._model_name = "gpt-4o"
    llm_service.complete_async = AsyncMock(return_value="Test response")

    # Create LLM Call agent with template vars in tool_properties
    llm_tool = LLMCallAgent(
        trace_manager=trace_manager,
        completion_service=llm_service,
        tool_description=ToolDescription(
            name="GenerateResponse",
            description="Generate a response with custom style",
            tool_properties={
                "username": {
                    "type": "string",
                    "description": "Name of the user",
                },
                "tone": {
                    "type": "string",
                    "description": "Tone of the response",
                },
                "question": {
                    "type": "string",
                    "description": "The question to answer",
                },
            },
            required_tool_properties=["username", "tone", "question"],
        ),
        component_attributes=ComponentAttributes(component_instance_name="Generate Response"),
        prompt_template="Hello {username}. Answer this question: {question}. Use a {tone} tone.",
        capability_resolver=make_capability_resolver(llm_service, {"openai:gpt-4o"}),
    )

    # Create ReAct agent with the LLM tool
    react = ReActAgent(
        completion_service=llm_service,
        component_attributes=ComponentAttributes(component_instance_name="ReAct"),
        trace_manager=trace_manager,
        tool_description=ToolDescription(
            name="react", description="", tool_properties={}, required_tool_properties=[]
        ),
        agent_tools=[llm_tool],
        run_tools_in_parallel=False,
    )

    # Simulate tool call with template vars as tool properties
    username = "Bob"
    tone = "friendly"
    question = "What is Python?"
    fn = SimpleNamespace(
        name="GenerateResponse",
        arguments=f'{{"messages": [], "username": "{username}", "tone": "{tone}", "question": "{question}"}}',
    )
    tool_call = SimpleNamespace(id="call_1", function=fn)

    # Tools receive legacy AgentPayload in this path
    agent_payload = AgentPayload(messages=[ChatMessage(role="user", content="Generate a response")])
    _id, _ = asyncio.run(react._run_tool_call(agent_payload, tool_call=tool_call))

    # Verify completion was called with template variables from tool properties
    llm_service.complete_async.assert_called_once()
    content = llm_service.complete_async.call_args.kwargs["messages"][0]["content"]

    # Check that template variables were used in the text content
    # Content can be a string or a list (if files are included)
    if isinstance(content, list):
        text_parts = [p for p in content if isinstance(p, dict) and p.get("type") == "text"]
        assert len(text_parts) == 1
        text_content = text_parts[0]["text"]
    else:
        text_content = content

    # Verify template variables were filled
    assert username in text_content, f"Expected '{username}' in content: {text_content}"
    assert tone in text_content, f"Expected '{tone}' in content: {text_content}"
    assert question in text_content, f"Expected '{question}' in content: {text_content}"
