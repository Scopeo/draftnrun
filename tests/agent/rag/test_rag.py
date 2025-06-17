import pytest
from unittest.mock import MagicMock, patch

from llama_index.llms.openai import OpenAI
from engine.agent.agent import SourceChunk
from engine.agent.rag.retriever import Retriever
from engine.agent.synthesizer import Synthesizer

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


@pytest.fixture
def mock_trace_manager():
    return MockTraceManager(project_name="project_name")


@pytest.fixture
def rag(mock_trace_manager):
    retriever = MagicMock(spec=Retriever)
    mock_synthesizer = MagicMock(spec=Synthesizer)
    retriever.get_chunks.return_value = [
        SourceChunk(name="SourceChunk_1", document_name="SourceChunk_1", url="url1", content="Result 1"),
        SourceChunk(name="SourceChunk_2", document_name="SourceChunk_2", url="url2", content="Result 2"),
    ]
    with patch("engine.agent.build_context.build_context_from_source_chunks") as mock_build_context_from_source_chunks:
        mock_build_context_from_source_chunks.return_value = "**Node 1:** Result 1\n\n**Node 2:** Result 2\n\n"
        mock_synthetizer_response = MagicMock()
        mock_synthetizer_response.response = (
            "Test Response [1][2]\n" "Sources:\n" "[1] <url1|SourceChunk_1>\n" "[2] <url2|SourceChunk_2>\n"
        )
        mock_synthetizer_response.sources = [
            SourceChunk(name="SourceChunk_1", document_name="SourceChunk_1", url="url1", content="Result 1"),
            SourceChunk(name="SourceChunk_2", document_name="SourceChunk_2", url="url2", content="Result 2"),
        ]
        mock_synthetizer_response.is_successful = True
        mock_synthesizer.get_response.return_value = mock_synthetizer_response

        return RAG(
            retriever=retriever,
            trace_manager=mock_trace_manager,
            synthesizer=mock_synthesizer,
            tool_description=MagicMock(),
        )


@pytest.fixture
def message_to_process():
    return AgentPayload(messages=[ChatMessage(role="user", content="Hello, world!")])


@patch.object(OpenAI, "complete")
def test_rag_run(mock_complete, rag, message_to_process):
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
