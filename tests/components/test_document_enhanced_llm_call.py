import copy
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from engine.components.document_enhanced_llm_call import (
    DEFAULT_DOCUMENT_ENHANCED_LLM_CALL_TOOL_DESCRIPTION,
    DocumentEnhancedLLMCallAgent,
    DocumentEnhancedLLMCallInputs,
    DocumentEnhancedLLMCallOutputs,
    build_ascii_tree,
)
from engine.components.types import ComponentAttributes, SourceChunk
from engine.trace.trace_manager import TraceManager


@pytest.fixture
def mock_trace_manager():
    tm = MagicMock(spec=TraceManager)
    tm.start_span.return_value.__enter__ = MagicMock(return_value=MagicMock())
    tm.start_span.return_value.__exit__ = MagicMock(return_value=False)
    return tm


@pytest.fixture
def sample_chunks():
    return [
        SourceChunk(name="chunk1", document_name="doc_a.pdf", content="Content of doc A"),
        SourceChunk(name="chunk2", document_name="doc_b.pdf", content="Content of doc B"),
    ]


@pytest.fixture
def mock_document_search(sample_chunks):
    ds = MagicMock()
    ds.get_documents_names.return_value = ["folder/doc_a.pdf", "folder/doc_b.pdf"]
    ds.get_documents.return_value = sample_chunks
    return ds


@pytest.fixture
def mock_synthesizer():
    synth = MagicMock()
    synth.get_response = AsyncMock(return_value=MagicMock(response="Synthesized answer", is_successful=True))
    return synth


@pytest.fixture
def component(mock_trace_manager, mock_document_search, mock_synthesizer):
    tool_description = copy.deepcopy(DEFAULT_DOCUMENT_ENHANCED_LLM_CALL_TOOL_DESCRIPTION)
    return DocumentEnhancedLLMCallAgent(
        trace_manager=mock_trace_manager,
        component_attributes=ComponentAttributes(component_instance_name="test_document_enhanced_llm_call"),
        tool_description=tool_description,
        synthesizer=mock_synthesizer,
        document_search=mock_document_search,
    )


# --- Schema / contract tests ---


def test_migrated_flag():
    assert DocumentEnhancedLLMCallAgent.migrated is True


def test_get_inputs_schema():
    assert DocumentEnhancedLLMCallAgent.get_inputs_schema() is DocumentEnhancedLLMCallInputs


def test_get_outputs_schema():
    assert DocumentEnhancedLLMCallAgent.get_outputs_schema() is DocumentEnhancedLLMCallOutputs


def test_get_canonical_ports():
    assert DocumentEnhancedLLMCallAgent.get_canonical_ports() == {"input": "query_text", "output": "output"}


# --- Constructor tests ---


def test_constructor_updates_tool_description_enum(component, mock_document_search):
    enum_values = component.tool_description.tool_properties["document_names"]["items"]["enum"]
    assert enum_values == mock_document_search.get_documents_names()


def test_constructor_appends_tree_to_description(component):
    assert "Here is the list of documents available" in component.tool_description.description
    assert component.tree_of_documents in component.tool_description.description


# --- Successful execution test ---


@pytest.mark.asyncio
async def test_run_returns_typed_outputs(component, sample_chunks):
    inputs = DocumentEnhancedLLMCallInputs(
        query_text="What is in doc A?",
        document_names=["folder/doc_a.pdf"],
    )
    result = await component._run_without_io_trace(inputs, ctx={})

    assert isinstance(result, DocumentEnhancedLLMCallOutputs)
    assert result.output == "Synthesized answer"
    assert result.is_final is True
    assert "documents" in result.artifacts
    assert len(result.artifacts["documents"]) == len(sample_chunks)


@pytest.mark.asyncio
async def test_run_calls_synthesizer_with_correct_args(component, mock_synthesizer):
    inputs = DocumentEnhancedLLMCallInputs(
        query_text="Summarize doc B",
        document_names=["folder/doc_b.pdf"],
    )
    await component._run_without_io_trace(inputs, ctx={})

    mock_synthesizer.get_response.assert_awaited_once()
    call_kwargs = mock_synthesizer.get_response.call_args
    assert call_kwargs.kwargs["query_str"] == "Summarize doc B"
    assert call_kwargs.kwargs["optional_contexts"] == {}


@pytest.mark.asyncio
async def test_run_calls_document_search_with_names(component, mock_document_search):
    inputs = DocumentEnhancedLLMCallInputs(
        query_text="Tell me about doc A",
        document_names=["folder/doc_a.pdf"],
    )
    await component._run_without_io_trace(inputs, ctx={})

    mock_document_search.get_documents.assert_called_once_with(documents_name=["folder/doc_a.pdf"])


# --- Error tests ---


@pytest.mark.asyncio
async def test_run_raises_when_query_text_is_none(component):
    inputs = DocumentEnhancedLLMCallInputs(
        query_text=None,
        document_names=["folder/doc_a.pdf"],
    )
    with pytest.raises(ValueError, match="No content provided"):
        await component._run_without_io_trace(inputs, ctx={})


@pytest.mark.asyncio
async def test_run_raises_when_document_names_is_none(component):
    inputs = DocumentEnhancedLLMCallInputs(
        query_text="some query",
        document_names=None,
    )
    with pytest.raises(ValueError, match="No document names provided"):
        await component._run_without_io_trace(inputs, ctx={})


# --- Trace logging test ---


@pytest.mark.asyncio
async def test_run_logs_trace_for_each_document(component, sample_chunks):
    inputs = DocumentEnhancedLLMCallInputs(
        query_text="Tell me about the documents",
        document_names=["folder/doc_a.pdf", "folder/doc_b.pdf"],
    )
    with patch.object(component, "log_trace") as mock_log_trace:
        await component._run_without_io_trace(inputs, ctx={})

    assert mock_log_trace.call_count == len(sample_chunks)


# --- build_ascii_tree utility test ---


def test_build_ascii_tree_empty():
    assert build_ascii_tree([]) == ""


def test_build_ascii_tree_flat_files():
    result = build_ascii_tree(["a.pdf", "b.pdf"])
    assert "a.pdf" in result
    assert "b.pdf" in result


def test_build_ascii_tree_nested():
    result = build_ascii_tree(["folder/a.pdf", "folder/b.pdf"])
    assert "folder" in result
    assert "a.pdf" in result
    assert "b.pdf" in result
