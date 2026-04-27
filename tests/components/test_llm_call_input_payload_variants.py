"""Test LLM Call agent with various input payload variants.

Tests for file_url, file_content, and template_vars from API input and as tool properties.
"""

import asyncio
import base64
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from engine.components.ai_agent import AIAgent
from engine.components.component import ComponentAttributes
from engine.components.llm_call import LLMCallAgent
from engine.components.types import AgentPayload, ChatMessage, NodeData, ToolDescription
from engine.trace.trace_manager import TraceManager
from tests.components.test_llm_call import make_capability_resolver


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
    llm_service._model_name = "gpt-5-mini"
    llm_service.complete_async = AsyncMock(return_value="Test response")

    with patch("engine.components.llm_call.CompletionService", return_value=llm_service):
        agent = LLMCallAgent(
            trace_manager=trace_manager,
            temperature=1.0,
            llm_api_key=None,
            model_id_resolver=lambda _: None,
            tool_description=ToolDescription(
                name="llm_call", description="llm_call", tool_properties={}, required_tool_properties=[]
            ),
            component_attributes=ComponentAttributes(component_instance_name="LLM Call"),
            file_url_key="document_url",
            capability_resolver=make_capability_resolver(llm_service, {"openai:gpt-5-mini"}),
        )

        file_url = "https://example.com/document.pdf"
        input_node_data = NodeData(
            data={
                "messages": [{"role": "user", "content": "Analyze this document"}],
                "prompt_template": "Process this file: {{input}}",
                "document_url": file_url,
            },
            ctx={},
        )

        result = asyncio.run(agent.run(input_node_data))

        assert result.data["output"] == "Test response"
        llm_service.complete_async.assert_called_once()
        content = llm_service.complete_async.call_args.kwargs["messages"][0]["content"]
        assert isinstance(content, list)

        file_parts = [p for p in content if isinstance(p, dict) and p.get("type") == "file" and "file_url" in p]
        assert len(file_parts) == 1
        assert file_parts[0]["file_url"] == file_url


@patch("engine.prometheus_metric.agent_calls")
@patch("engine.prometheus_metric.get_tracing_span")
def test_file_content_from_api_input(get_span_mock, agent_calls_mock):
    """Test file_content from API input (NodeData.data) for block LLM Call."""
    get_span_mock.return_value = MagicMock(project_id="test_project")
    counter_mock = MagicMock()
    agent_calls_mock.labels.return_value = counter_mock

    trace_manager = MagicMock(spec=TraceManager)
    llm_service = MagicMock()
    llm_service._provider = "openai"
    llm_service._model_name = "gpt-5-mini"
    llm_service.complete_async = AsyncMock(return_value="Test response")

    with patch("engine.components.llm_call.CompletionService", return_value=llm_service):
        agent = LLMCallAgent(
            trace_manager=trace_manager,
            temperature=1.0,
            llm_api_key=None,
            model_id_resolver=lambda _: None,
            tool_description=ToolDescription(
                name="llm_call", description="llm_call", tool_properties={}, required_tool_properties=[]
            ),
            component_attributes=ComponentAttributes(component_instance_name="LLM Call"),
            file_content_key="document_file",
            capability_resolver=make_capability_resolver(llm_service, {"openai:gpt-5-mini"}),
        )

        sample_pdf_path = Path(__file__).parent.parent / "resources" / "documents" / "sample.pdf"
        with open(sample_pdf_path, "rb") as f:
            pdf_content = f.read()
        pdf_base64 = base64.b64encode(pdf_content).decode("utf-8")
        file_data = f"data:application/pdf;base64,{pdf_base64}"

        input_node_data = NodeData(
            data={
                "messages": [{"role": "user", "content": "Analyze this document"}],
                "prompt_template": "Process this file: {{input}}",
                "document_file": {
                    "filename": "sample.pdf",
                    "file_data": file_data,
                },
            },
            ctx={},
        )

        result = asyncio.run(agent.run(input_node_data))

        assert result.data["output"] == "Test response"
        llm_service.complete_async.assert_called_once()
        content = llm_service.complete_async.call_args.kwargs["messages"][0]["content"]
        assert isinstance(content, list)

        file_parts = [p for p in content if isinstance(p, dict) and p.get("type") == "file" and "file" in p]
        assert len(file_parts) == 1
        assert file_parts[0]["file"]["filename"] == "sample.pdf"
        assert file_parts[0]["file"]["file_data"] == file_data


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
    llm_service._model_name = "gpt-5-mini"
    llm_service.complete_async = AsyncMock(return_value="Test response")

    with patch("engine.components.llm_call.CompletionService", return_value=llm_service):
        agent = LLMCallAgent(
            trace_manager=trace_manager,
            temperature=1.0,
            llm_api_key=None,
            model_id_resolver=lambda _: None,
            tool_description=ToolDescription(
                name="llm_call", description="llm_call", tool_properties={}, required_tool_properties=[]
            ),
            component_attributes=ComponentAttributes(component_instance_name="LLM Call"),
            capability_resolver=make_capability_resolver(llm_service, {"openai:gpt-5-mini"}),
        )

        input_node_data = NodeData(
            data={
                "messages": [{"role": "user", "content": "What is AI?"}],
                "prompt_template": "Hello {{username}}, answer this: {{input}}. Use style: {{style}}",
                "username": "Alice",
                "style": "formal",
            },
            ctx={},
        )

        result = asyncio.run(agent.run(input_node_data))

        assert result.data["output"] == "Test response"
        llm_service.complete_async.assert_called_once()
        content = llm_service.complete_async.call_args.kwargs["messages"][0]["content"]

        if isinstance(content, list):
            text_parts = [p for p in content if isinstance(p, dict) and p.get("type") == "text"]
            assert len(text_parts) == 1
            text_content = text_parts[0]["text"]
        else:
            text_content = content

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
    llm_service._model_name = "gpt-5-mini"
    llm_service.complete_async = AsyncMock(return_value="Test response")

    with (
        patch("engine.components.llm_call.CompletionService", return_value=llm_service),
        patch("engine.components.ai_agent.CompletionService", return_value=llm_service),
    ):
        llm_tool = LLMCallAgent(
            trace_manager=trace_manager,
            temperature=1.0,
            llm_api_key=None,
            model_id_resolver=lambda _: None,
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
            file_url_key="document_url",
            capability_resolver=make_capability_resolver(llm_service, {"openai:gpt-5-mini"}),
        )

        react = AIAgent(
            temperature=1.0,
            llm_api_key=None,
            model_id_resolver=lambda _: None,
            component_attributes=ComponentAttributes(component_instance_name="ReAct"),
            trace_manager=trace_manager,
            tool_description=ToolDescription(
                name="react", description="", tool_properties={}, required_tool_properties=[]
            ),
            agent_tools=[llm_tool],
            run_tools_in_parallel=False,
        )

        document_url = "https://example.com/report.pdf"
        fn = SimpleNamespace(
            name="AnalyzeDocument",
            arguments=(
                f'{{"messages": [], "prompt_template": "Analyze this document.", "document_url": "{document_url}"}}'
            ),
        )
        tool_call = SimpleNamespace(id="call_1", function=fn)

        agent_payload = AgentPayload(messages=[ChatMessage(role="user", content="Analyze the document")])
        _id, _ = asyncio.run(react._run_tool_call(agent_payload, tool_call=tool_call))

        llm_service.complete_async.assert_called_once()
        content = llm_service.complete_async.call_args.kwargs["messages"][0]["content"]
        assert isinstance(content, list)

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
    llm_service._model_name = "gpt-5-mini"
    llm_service.complete_async = AsyncMock(return_value="Test response")

    with (
        patch("engine.components.llm_call.CompletionService", return_value=llm_service),
        patch("engine.components.ai_agent.CompletionService", return_value=llm_service),
    ):
        llm_tool = LLMCallAgent(
            trace_manager=trace_manager,
            temperature=1.0,
            llm_api_key=None,
            model_id_resolver=lambda _: None,
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
            capability_resolver=make_capability_resolver(llm_service, {"openai:gpt-5-mini"}),
        )

        react = AIAgent(
            temperature=1.0,
            llm_api_key=None,
            model_id_resolver=lambda _: None,
            component_attributes=ComponentAttributes(component_instance_name="ReAct"),
            trace_manager=trace_manager,
            tool_description=ToolDescription(
                name="react", description="", tool_properties={}, required_tool_properties=[]
            ),
            agent_tools=[llm_tool],
            run_tools_in_parallel=False,
        )

        username = "Bob"
        tone = "friendly"
        question = "What is Python?"
        fn = SimpleNamespace(
            name="GenerateResponse",
            arguments=(
                f'{{"messages": [], "prompt_template": "Hello {{{{username}}}}. Answer this '
                f'question: {{{{question}}}}. Use a {{{{tone}}}} tone.", "username": "{username}", "tone": "{tone}", '
                f'"question": "{question}"}}'
            ),
        )
        tool_call = SimpleNamespace(id="call_1", function=fn)

        agent_payload = AgentPayload(messages=[ChatMessage(role="user", content="Generate a response")])
        _id, _ = asyncio.run(react._run_tool_call(agent_payload, tool_call=tool_call))

        llm_service.complete_async.assert_called_once()
        content = llm_service.complete_async.call_args.kwargs["messages"][0]["content"]

        if isinstance(content, list):
            text_parts = [p for p in content if isinstance(p, dict) and p.get("type") == "text"]
            assert len(text_parts) == 1
            text_content = text_parts[0]["text"]
        else:
            text_content = content

        assert username in text_content, f"Expected '{username}' in content: {text_content}"
        assert tone in text_content, f"Expected '{tone}' in content: {text_content}"
        assert question in text_content, f"Expected '{question}' in content: {text_content}"
