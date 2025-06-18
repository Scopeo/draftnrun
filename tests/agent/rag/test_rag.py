import pytest
from unittest.mock import MagicMock, patch

from llama_index.llms.openai import OpenAI
from engine.agent.agent import SourceChunk
from engine.agent.rag.retriever import Retriever
from engine.agent.synthesizer import Synthesizer
from engine.llm_services.llm_service import LLMService
from engine.agent.agent import AgentPayload, ChatMessage
from engine.agent.rag.rag import RAG
from tests.mocks.trace_manager import MockTraceManager


class MockEmbedding:
    def __init__(self, embedding):
        self.embedding = embedding


class MockQdrantResult:
    def __init__(self, name, content):
        self.score = 0.5
        self.payload = {"name": name, "content": content}


class CaptureLLMService(LLMService):
    def __init__(self, default_response: str):
        self.last_prompt = None
        self.default_response = default_response

    def constrained_complete(self, messages: list[dict], response_format: type):
        self.last_prompt = messages[0]["content"]
        return response_format(response=self.default_response, is_successful=True)

    # Stub implementations for abstract methods (no-op or dummy)
    def complete(self, *args, **kwargs):
        raise NotImplementedError("Not used in this test")

    def complete_with_files(self, *args, **kwargs):
        raise NotImplementedError("Not used in this test")

    def embed(self, *args, **kwargs):
        raise NotImplementedError("Not used in this test")

    def _format_image_content(self, *args, **kwargs):
        raise NotImplementedError("Not used in this test")

    def _function_call_without_trace(self, *args, **kwargs):
        raise NotImplementedError("Not used in this test")

    def generate_speech_from_text(self, *args, **kwargs):
        raise NotImplementedError("Not used in this test")

    def generate_transcript(self, *args, **kwargs):
        raise NotImplementedError("Not used in this test")

    def get_token_size(self, *args, **kwargs):
        raise NotImplementedError("Not used in this test")


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
def test_rag_run(mock_complete, mock_trace_manager, mock_retriever, mock_synthesizer, message_to_process):

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
    assert all(isinstance(source, SourceChunk) for source in output.artifacts["sources"])
    assert output.artifacts["sources"][0].name == results[0].payload["name"]
    assert output.artifacts["sources"][0].content == results[0].payload["content"]
    assert output.artifacts["sources"][1].name == results[1].payload["name"]
    assert output.artifacts["sources"][1].content == results[1].payload["content"]


def test_vocabulary_rag_run(mock_trace_manager, mock_retriever):
    capture_llm_service = CaptureLLMService(
        default_response="Test Response [1][2]\nSources:\n[1] <url1|SourceChunk_1>\n[2] <url2|SourceChunk_2>\n"
    )
    prompt_template = "{context_str} ---\n{vocabulary_context_str}\n---{query_str}"
    vocabulary_context = {"term": ["term1", "term2"], "definition": ["definition1", "definition2"]}
    rag = RAG(
        retriever=mock_retriever,
        trace_manager=mock_trace_manager,
        synthesizer=Synthesizer(
            llm_service=capture_llm_service, prompt_template=prompt_template, trace_manager=mock_trace_manager
        ),
        tool_description=MagicMock(),
        vocabulary_context=vocabulary_context,
        vocabulary_context_prompt_key="vocabulary_context_str",
        fuzzy_matching_candidates=10,
        fuzzy_threshold=90,
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
    assert all(isinstance(source, SourceChunk) for source in output.artifacts["sources"])
    assert output.artifacts["sources"][0].name == results[0].payload["name"]
    assert output.artifacts["sources"][0].content == results[0].payload["content"]
    assert output.artifacts["sources"][1].name == results[1].payload["name"]
    assert output.artifacts["sources"][1].content == results[1].payload["content"]
    assert (
        capture_llm_service.last_prompt == "**Source 1:**\nResult 1\n\n**Source 2:**\nResult 2 ---"
        "\n**Glossary definition of term1:**\ndefinition1\n\n**Glossary definition of term2:"
        "**\ndefinition2\n---What is the definition of term1 and term2?"
    )
