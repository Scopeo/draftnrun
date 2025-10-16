import json
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from types import SimpleNamespace

import pytest
import networkx as nx

from engine.agent.inputs_outputs.input import Input, DEFAULT_INPUT_TOOL_DESCRIPTION
from engine.agent.react_function_calling import ReActAgent
from engine.agent.types import AgentPayload, ToolDescription, ComponentAttributes, SourceChunk
from engine.agent.rag.rag import RAG
from engine.agent.rag.retriever import Retriever
from engine.agent.synthesizer import Synthesizer
from engine.graph_runner.graph_runner import GraphRunner
from engine.llm_services.llm_service import CompletionService
from engine.qdrant_service import QdrantService


@pytest.fixture
def input_component(mock_trace_manager):
    """Input component fixture."""
    payload_schema = json.dumps({"messages": [], "check_template": "", "rag_filter": {}})

    return Input(
        trace_manager=mock_trace_manager,
        tool_description=DEFAULT_INPUT_TOOL_DESCRIPTION,
        component_attributes=ComponentAttributes(component_instance_name="input_component"),
        payload_schema=payload_schema,
    )


@pytest.fixture
def mock_qdrant_service():
    """Mock Qdrant service that captures filter usage."""
    mock_qdrant = MagicMock(spec=QdrantService)
    mock_qdrant.captured_filters = []

    mock_embedding_service = MagicMock()
    mock_embedding_service._model_name = "test_embedding_model"
    mock_qdrant._embedding_service = mock_embedding_service

    async def mock_retrieve_similar_chunks_async(query_text, collection_name, filter=None, **kwargs):
        mock_qdrant.captured_filters.append(filter)

        return [
            SourceChunk(
                name="test_chunk_1",
                content="Test content 1",
                document_name="test_doc_1",
                url="https://test.com/doc1",
                metadata={},
            ),
            SourceChunk(
                name="test_chunk_2",
                content="Test content 2",
                document_name="test_doc_2",
                url="https://test.com/doc2",
                metadata={},
            ),
        ]

    mock_qdrant.retrieve_similar_chunks_async = AsyncMock(side_effect=mock_retrieve_similar_chunks_async)
    return mock_qdrant


@pytest.fixture
def real_rag_component(mock_trace_manager, mock_qdrant_service):
    retriever = Retriever(
        qdrant_service=mock_qdrant_service,
        trace_manager=mock_trace_manager,
        collection_name="test_collection",
        max_retrieved_chunks=5,
    )
    mock_synthesizer_llm = MagicMock(spec=CompletionService)
    mock_synthesizer_llm._model_name = "test_synthesizer_model"
    mock_synthesizer_llm._provider = "openai"

    from engine.agent.synthesizer import SynthesizerResponse

    mock_synthesizer_response = SynthesizerResponse(response="Mock RAG response based on context", is_successful=True)
    mock_synthesizer_llm.constrained_complete_with_pydantic_async = AsyncMock(return_value=mock_synthesizer_response)

    synthesizer = Synthesizer(
        completion_service=mock_synthesizer_llm,
        prompt_template="Context: {context_str}\n\nQuery: {query_str}",
        trace_manager=mock_trace_manager,
    )

    tool_description = ToolDescription(
        name="rag_search",
        description="Search for information using RAG",
        tool_properties={
            "query_text": {"type": "string", "description": "Search query"},
            "filters": {"type": "object", "description": "Search filters"},
        },
        required_tool_properties=["query_text"],
    )

    rag = RAG(
        trace_manager=mock_trace_manager,
        tool_description=tool_description,
        retriever=retriever,
        synthesizer=synthesizer,
        component_attributes=ComponentAttributes(component_instance_name="rag_component"),
    )

    return rag


@patch("engine.prometheus_metric.get_tracing_span")
@patch("engine.prometheus_metric.agent_calls")
def test_template_variable_injection(
    agent_calls_mock, get_span_mock, input_component, mock_trace_manager, mock_llm_service, real_rag_component
):
    get_span_mock.return_value.project_id = "test_project"
    counter_mock = MagicMock()
    agent_calls_mock.labels.return_value = counter_mock

    rag_component = real_rag_component

    tool_description = ToolDescription(
        name="react_agent", description="A ReAct agent for testing", tool_properties={}, required_tool_properties=[]
    )

    react_agent = ReActAgent(
        completion_service=mock_llm_service,
        component_attributes=ComponentAttributes(component_instance_name="react_agent"),
        agent_tools=[rag_component],
        trace_manager=mock_trace_manager,
        tool_description=tool_description,
        initial_prompt="You are a helpful assistant. User query: {check_template}. Search"
        " for information when needed.",
    )

    g = nx.DiGraph()
    g.add_nodes_from(["input", "react_agent"])
    g.add_edge("input", "react_agent")

    runnables = {"input": input_component, "react_agent": react_agent}

    # Explicit port mappings: input.messages -> react_agent.messages, input.rag_filter -> react_agent.rag_filter
    port_mappings = [
        {
            "source_instance_id": "input",
            "source_port_name": "messages",
            "target_instance_id": "react_agent",
            "target_port_name": "messages",
            "dispatch_strategy": "direct",
        },
        {
            "source_instance_id": "input",
            "source_port_name": "rag_filter",
            "target_instance_id": "react_agent",
            "target_port_name": "rag_filter",
            "dispatch_strategy": "direct",
        },
    ]

    gr = GraphRunner(
        graph=g,
        runnables=runnables,
        start_nodes=["input"],
        trace_manager=mock_trace_manager,
        port_mappings=port_mappings,
    )

    input_payload = {
        "messages": [{"role": "user", "content": "search for information"}],
        "check_template": "weather_info",
    }

    result = asyncio.run(gr.run(input_payload))

    assert isinstance(result, AgentPayload)

    assert mock_llm_service.function_call_async.call_count >= 1
    first_call = mock_llm_service.function_call_async.call_args_list[0]
    called_messages = first_call.kwargs["messages"]
    system_message = called_messages[0]
    assert system_message["role"] == "system"
    assert "weather_info" in system_message["content"]  # Template variable should be substituted


@patch("engine.prometheus_metric.get_tracing_span")
@patch("engine.prometheus_metric.agent_calls")
def test_rag_filter_superseding_react_function_calling_rag_filter(
    agent_calls_mock,
    get_span_mock,
    input_component,
    mock_trace_manager,
    mock_llm_service,
    real_rag_component,
    mock_qdrant_service,
):
    get_span_mock.return_value.project_id = "test_project"
    counter_mock = MagicMock()
    agent_calls_mock.labels.return_value = counter_mock

    rag_component = real_rag_component

    from openai.types.chat import ChatCompletionMessageToolCall
    from openai.types.chat.chat_completion_message_tool_call import Function

    mock_tool_call = ChatCompletionMessageToolCall(
        id="rag_call_1",
        function=Function(
            name="rag_search",
            arguments=json.dumps(
                {"query_text": "search query", "filters": {"ai_generated": True, "source": "ai_agent"}}
            ),
        ),
        type="function",
    )

    mock_response_message = SimpleNamespace(
        role="assistant",
        content="I'll search for information",
        tool_calls=[mock_tool_call],
        model_dump=lambda: {
            "role": "assistant",
            "content": "I'll search for information",
            "tool_calls": [
                {
                    "id": "rag_call_1",
                    "function": {
                        "name": "rag_search",
                        "arguments": json.dumps(
                            {"query_text": "search query", "filters": {"ai_generated": True, "source": "ai_agent"}}
                        ),
                    },
                    "type": "function",
                }
            ],
        },
    )

    choice = SimpleNamespace(message=mock_response_message)
    response = SimpleNamespace(choices=[choice])

    tool_description = ToolDescription(
        name="react_agent", description="A ReAct agent for testing", tool_properties={}, required_tool_properties=[]
    )

    react_agent = ReActAgent(
        completion_service=mock_llm_service,
        component_attributes=ComponentAttributes(component_instance_name="react_agent"),
        agent_tools=[rag_component],
        trace_manager=mock_trace_manager,
        tool_description=tool_description,
        initial_prompt="You are a helpful assistant. Search for information when needed.",
    )

    final_message = SimpleNamespace(
        role="assistant",
        content="Final response after RAG search",
        tool_calls=None,
        model_dump=lambda: {"role": "assistant", "content": "Final response after RAG search", "tool_calls": None},
    )
    choice = SimpleNamespace(message=final_message)
    final_response = SimpleNamespace(choices=[choice])

    mock_llm_service.function_call_async = AsyncMock(side_effect=[response, final_response])

    # Create graph: Input -> React Agent with explicit port mappings
    g = nx.DiGraph()
    g.add_nodes_from(["input", "react_agent"])
    g.add_edge("input", "react_agent")

    runnables = {"input": input_component, "react_agent": react_agent}

    # Explicit port mappings: input.messages -> react_agent.messages, input.rag_filter -> react_agent.rag_filter
    port_mappings = [
        {
            "source_instance_id": "input",
            "source_port_name": "messages",
            "target_instance_id": "react_agent",
            "target_port_name": "messages",
            "dispatch_strategy": "direct",
        },
        {
            "source_instance_id": "input",
            "source_port_name": "rag_filter",
            "target_instance_id": "react_agent",
            "target_port_name": "rag_filter",
            "dispatch_strategy": "direct",
        },
    ]

    gr = GraphRunner(
        graph=g,
        runnables=runnables,
        start_nodes=["input"],
        trace_manager=mock_trace_manager,
        port_mappings=port_mappings,
    )

    input_payload = {
        "messages": [{"role": "user", "content": "search for information"}],
        "rag_filter": {"source": "user_input", "topic": "weather", "override": True},
    }

    result = asyncio.run(gr.run(input_payload))

    assert isinstance(result, AgentPayload)

    assert len(mock_qdrant_service.captured_filters) > 0

    last_filters = mock_qdrant_service.captured_filters[-1]

    assert last_filters == {"source": "user_input", "topic": "weather", "override": True}
