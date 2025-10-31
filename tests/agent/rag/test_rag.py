import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from llama_index.llms.openai import OpenAI
from engine.agent.types import SourceChunk
from engine.agent.rag.retriever import Retriever
from engine.agent.synthesizer import Synthesizer
from engine.agent.rag.vocabulary_search import VocabularySearch
from engine.llm_services.llm_service import CompletionService
from engine.agent.types import AgentPayload, ChatMessage
from engine.agent.rag.rag import RAG
from tests.mocks.trace_manager import MockTraceManager


class MockEmbedding:
    def __init__(self, embedding):
        self.embedding = embedding


class MockQdrantResult:
    def __init__(self, name, content):
        self.score = 0.5
        self.payload = {"name": name, "content": content}


@pytest.fixture
def make_mock_llm_service():
    def _make_mock(default_response: str):
        mock_llm = MagicMock(spec=CompletionService)
        mock_llm.last_prompt = None
        mock_llm._model_name = "mock_model"

        from engine.agent.synthesizer import SynthesizerResponse

        mock_response = SynthesizerResponse(response=default_response, is_successful=True)

        async def constrained_complete_with_pydantic_async(messages, response_format):
            mock_llm.last_prompt = messages
            return mock_response

        mock_llm.constrained_complete_with_pydantic_async = AsyncMock(
            side_effect=constrained_complete_with_pydantic_async
        )
        mock_llm._provider = "openai"
        return mock_llm

    return _make_mock


@pytest.fixture
def mock_trace_manager():
    return MockTraceManager(project_name="project_name")


@pytest.fixture
def mock_retriever():
    retriever = MagicMock(spec=Retriever)
    retriever.get_chunks.return_value = [
        SourceChunk(name="SourceChunk_1", document_name="SourceChunk_1", url="url1", content="Result 1"),
        SourceChunk(name="SourceChunk_2", document_name="SourceChunk_2", url="url2", content="Result 2"),
    ]
    return retriever


@pytest.fixture
def mock_synthesizer():
    with patch("engine.agent.build_context.build_context_from_source_chunks") as mock_build_context:
        mock_build_context.return_value = "**Node 1:** Result 1\n\n**Node 2:** Result 2\n\n"

        mock_synthesizer = MagicMock(spec=Synthesizer)
        mock_response = MagicMock()
        mock_response.response = "Test Response [1][2]\nSources:\n[1] <url1|SourceChunk_1>\n[2] <url2|SourceChunk_2>\n"
        mock_response.sources = [
            SourceChunk(name="SourceChunk_1", document_name="SourceChunk_1", url="url1", content="Result 1"),
            SourceChunk(name="SourceChunk_2", document_name="SourceChunk_2", url="url2", content="Result 2"),
        ]
        mock_response.is_successful = True

        mock_synthesizer.get_response.return_value = mock_response
        return mock_synthesizer


@pytest.fixture
def message_to_process():
    return AgentPayload(messages=[ChatMessage(role="user", content="Hello, world!")])


@patch.object(OpenAI, "complete")
@patch("engine.prometheus_metric.get_tracing_span")
@patch("engine.prometheus_metric.agent_calls")
def test_rag_run(
    agent_calls_mock,
    get_span_mock,
    mock_complete,
    mock_trace_manager,
    mock_retriever,
    mock_synthesizer,
    message_to_process,
):
    get_span_mock.return_value.project_id = "1234"
    counter_mock = MagicMock()
    agent_calls_mock.labels.return_value = counter_mock
    rag = RAG(
        retriever=mock_retriever,
        trace_manager=mock_trace_manager,
        synthesizer=mock_synthesizer,
        tool_description=MagicMock(),
    )

    results = [
        MockQdrantResult(name="SourceChunk_1", content="Result 1"),
        MockQdrantResult(name="SourceChunk_2", content="Result 2"),
    ]
    response_text = "Test Response [1][2]\n" "Sources:\n" "[1] <url1|SourceChunk_1>\n" "[2] <url2|SourceChunk_2>\n"
    mock_complete.return_value.text = response_text

    output = rag.run_sync(message_to_process)
    assert output.last_message.content == response_text
    assert isinstance(output.artifacts["sources"], list)
    rehydrated_sources = [SourceChunk(**s) if isinstance(s, dict) else s for s in output.artifacts["sources"]]
    assert all(isinstance(source, SourceChunk) for source in rehydrated_sources)
    assert rehydrated_sources[0].name == results[0].payload["name"]
    assert rehydrated_sources[0].content == results[0].payload["content"]
    assert rehydrated_sources[1].name == results[1].payload["name"]
    assert rehydrated_sources[1].content == results[1].payload["content"]


@patch("engine.prometheus_metric.get_tracing_span")
@patch("engine.prometheus_metric.agent_calls")
def test_vocabulary_rag_run(
    agent_calls_mock, get_span_mock, make_mock_llm_service, mock_trace_manager, mock_retriever
):
    get_span_mock.return_value.project_id = "1234"
    counter_mock = MagicMock()
    agent_calls_mock.labels.return_value = counter_mock
    mock_llm_service = make_mock_llm_service(
        default_response="Test Response [1][2]\nSources:\n[1] <url1|SourceChunk_1>\n[2] <url2|SourceChunk_2>\n"
    )
    prompt_template = "{context_str} ---\n{vocabulary_context_str}\n---{query_str}"
    vocabulary_context = {"term": ["term1", "term2"], "definition": ["definition1", "definition2"]}
    vocabulary_search = VocabularySearch(
        trace_manager=mock_trace_manager,
        vocabulary_context_data=vocabulary_context,
        vocabulary_context_prompt_key="vocabulary_context_str",
        fuzzy_matching_candidates=10,
    )
    rag = RAG(
        retriever=mock_retriever,
        trace_manager=mock_trace_manager,
        synthesizer=Synthesizer(
            completion_service=mock_llm_service, prompt_template=prompt_template, trace_manager=mock_trace_manager
        ),
        vocabulary_search=vocabulary_search,
        tool_description=MagicMock(),
    )
    message_to_process = AgentPayload(
        messages=[ChatMessage(role="user", content="What is the definition of term1 and term2?")]
    )
    output = rag.run_sync(message_to_process)
    results = [
        MockQdrantResult(name="SourceChunk_1", content="Result 1"),
        MockQdrantResult(name="SourceChunk_2", content="Result 2"),
    ]
    assert (
        output.last_message.content
        == "Test Response [1][2]\nSources:\n[1] <url1|SourceChunk_1>\n[2] <url2|SourceChunk_2>\n"
    )
    assert isinstance(output.artifacts["sources"], list)
    rehydrated_sources = [SourceChunk(**s) if isinstance(s, dict) else s for s in output.artifacts["sources"]]
    assert all(isinstance(source, SourceChunk) for source in rehydrated_sources)
    assert rehydrated_sources[0].name == results[0].payload["name"]
    assert rehydrated_sources[0].content == results[0].payload["content"]
    assert rehydrated_sources[1].name == results[1].payload["name"]
    assert rehydrated_sources[1].content == results[1].payload["content"]
    assert (
        mock_llm_service.last_prompt == "**Source 1:**\nResult 1\n\n**Source 2:**\nResult 2 ---"
        "\n**Glossary definition of term1:**\ndefinition1\n\n**Glossary definition of term2:"
        "**\ndefinition2\n---What is the definition of term1 and term2?"
    )


@pytest.fixture
def mock_retriever_with_tracking():
    """Create a mock retriever that tracks the filters passed to get_chunks."""
    retriever = MagicMock(spec=Retriever)
    retriever.get_chunks = AsyncMock(
        return_value=[
            SourceChunk(name="SourceChunk_1", document_name="SourceChunk_1", url="url1", content="Result 1"),
        ]
    )
    return retriever


@patch("engine.prometheus_metric.get_tracing_span")
@patch("engine.prometheus_metric.agent_calls")
@pytest.mark.parametrize(
    "input_filters,context_rag_filter,expected_filter",
    [
        # Case 1: input_filter with value, rag_filter with value -> both combined in must
        (
            {"must": [{"key": "priority", "match": {"value": "high"}}]},
            {"must": [{"key": "department", "match": {"value": "HR"}}]},
            {
                "must": [
                    {"must": [{"key": "priority", "match": {"value": "high"}}]},
                    {"must": [{"key": "department", "match": {"value": "HR"}}]},
                ]
            },
        ),
        # Case 2: input_filter with None, rag_filter with value -> rag_filter
        (
            None,
            {"must": [{"key": "department", "match": {"value": "HR"}}]},
            {"must": [{"key": "department", "match": {"value": "HR"}}]},
        ),
        # Case 3: input_filter with empty dict, rag_filter with value -> rag_filter
        (
            {},
            {"must": [{"key": "department", "match": {"value": "HR"}}]},
            {"must": [{"key": "department", "match": {"value": "HR"}}]},
        ),
        # Case 4: input_filter with value, rag_filter not in context -> input_filter
        (
            {"must": [{"key": "priority", "match": {"value": "high"}}]},
            None,
            {"must": [{"key": "priority", "match": {"value": "high"}}]},
        ),
        # Case 5: input_filter at None, no rag_filter -> filter_used = None
        (
            None,
            None,
            None,
        ),
    ],
)
def test_rag_filter_priority(
    agent_calls_mock,
    get_span_mock,
    mock_trace_manager,
    mock_retriever_with_tracking,
    mock_synthesizer,
    input_filters,
    context_rag_filter,
    expected_filter,
):
    """Test that RAG filter combination logic works correctly."""
    get_span_mock.return_value.project_id = "1234"
    counter_mock = MagicMock()
    agent_calls_mock.labels.return_value = counter_mock

    rag = RAG(
        retriever=mock_retriever_with_tracking,
        trace_manager=mock_trace_manager,
        synthesizer=mock_synthesizer,
        tool_description=MagicMock(),
    )

    mock_retriever_with_tracking.get_chunks.reset_mock()

    message_data = {"messages": [ChatMessage(role="user", content="test query")]}
    if input_filters is not None:
        message_data["filters"] = input_filters

    message = AgentPayload(**message_data)

    ctx = {}
    if context_rag_filter is not None:
        ctx["rag_filter"] = context_rag_filter

    rag.run_sync(message, ctx=ctx)

    mock_retriever_with_tracking.get_chunks.assert_called_once()
    call_args = mock_retriever_with_tracking.get_chunks.call_args
    assert call_args[1]["filters"] == expected_filter
