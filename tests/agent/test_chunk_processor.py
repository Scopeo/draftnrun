"""
Test module for ChunkProcessor functionality.
Tests the ability to split input data, process each chunk with a graph runner, and merge results.
"""

import asyncio
import uuid
from unittest.mock import MagicMock, patch

import networkx as nx
import pytest

from engine.agent.chunk_processor import ChunkProcessor
from engine.agent.types import AgentPayload, ChatMessage, ComponentAttributes
from engine.graph_runner.graph_runner import GraphRunner
from tests.mocks.dummy_agent import DummyAgent


@pytest.fixture
def mock_trace_manager():
    """Mock trace manager that returns a context manager."""

    trace_manager = MagicMock()
    mock_span = MagicMock()
    mock_span.__enter__ = MagicMock(return_value=mock_span)
    mock_span.__exit__ = MagicMock(return_value=None)
    trace_manager.start_span.return_value = mock_span
    mock_span.to_json.return_value = '{"context": {"trace_id": "testid"}, "attributes": {}, "parent_id": null}'
    return trace_manager


@pytest.fixture
def simple_graph_runner(mock_trace_manager):
    """Create a simple graph runner with dummy agent."""
    agent = DummyAgent(mock_trace_manager, "PROCESSED", "test")

    graph = nx.DiGraph()
    runnables = {"agent": agent}
    start_nodes = ["agent"]

    return GraphRunner(
        graph=graph,
        runnables=runnables,
        start_nodes=start_nodes,
        trace_manager=mock_trace_manager,
    )


def test_split_method():
    """Test the _split method splits input correctly."""
    chunk_processor = ChunkProcessor(
        trace_manager=MagicMock(),
        graph_runner=MagicMock(),
        component_attributes=ComponentAttributes(
            component_instance_id=uuid.uuid4(),
            component_instance_name="test",
        ),
        split_char=" ",
    )

    # Test with normal input split by space
    input_payload = AgentPayload(messages=[ChatMessage(role="user", content="word1 word2 word3")])
    chunks = chunk_processor._split(input_payload)

    assert len(chunks) == 3
    assert [c.messages[0].content for c in chunks] == ["word1", "word2", "word3"]

    # Test with fewer words than chunks
    input_payload = AgentPayload(messages=[ChatMessage(role="user", content="word1  word2")])
    chunks = chunk_processor._split(input_payload)

    assert len(chunks) == 2
    assert chunks[0].messages[0].content == "word1"
    assert chunks[1].messages[0].content == "word2"

    # Test with empty input
    input_payload = AgentPayload(messages=[ChatMessage(role="user", content="")])
    chunks = chunk_processor._split(input_payload)

    assert len(chunks) == 0


def test_merge_method():
    """Test the _merge method combines results correctly."""
    chunk_processor = ChunkProcessor(
        trace_manager=MagicMock(),
        graph_runner=MagicMock(),
        component_attributes=ComponentAttributes(
            component_instance_id=uuid.uuid4(),
            component_instance_name="test",
        ),
        join_char=" | ",
    )

    # Test merging multiple results
    results = [
        AgentPayload(messages=[ChatMessage(role="assistant", content="result1")]),
        AgentPayload(messages=[ChatMessage(role="assistant", content="result2")]),
        AgentPayload(messages=[ChatMessage(role="assistant", content="result3")]),
    ]

    merged = chunk_processor._merge(results)

    assert isinstance(merged, AgentPayload)
    assert len(merged.messages) == 1
    assert merged.messages[0].content == "result1 | result2 | result3"

    # Test with empty results
    merged = chunk_processor._merge([])
    assert merged.messages[0].content == ""


@patch("engine.prometheus_metric.get_tracing_span")
@patch("engine.prometheus_metric.agent_calls")
def test_chunk_processor_end_to_end(mock_agent_calls, mock_get_tracing_span, simple_graph_runner, mock_trace_manager):
    """Test the complete chunk processor workflow."""
    mock_get_tracing_span.return_value = MagicMock()
    chunk_processor = ChunkProcessor(
        trace_manager=mock_trace_manager,
        graph_runner=simple_graph_runner,
        component_attributes=ComponentAttributes(
            component_instance_id=uuid.uuid4(),
            component_instance_name="test",
        ),
        split_char=" ",
        join_char=" || ",
    )

    # Test processing
    input_payload = AgentPayload(messages=[ChatMessage(role="user", content="hello world")])
    result = asyncio.run(chunk_processor.run(input_payload))

    # Should get processed chunks joined
    assert isinstance(result, AgentPayload)
    assert len(result.messages) == 1
    assert " || " in result.messages[0].content
    assert "[PROCESSED]" in result.messages[0].content


def test_chunk_processor_parameters(mock_trace_manager, simple_graph_runner):
    """Test ChunkProcessor initialization with different parameters."""
    for split_char in [" ", ",", "\n\n"]:
        chunk_processor = ChunkProcessor(
            trace_manager=mock_trace_manager,
            graph_runner=simple_graph_runner,
            component_attributes=ComponentAttributes(
                component_instance_id=uuid.uuid4(),
                component_instance_name=f"test_{split_char}",
            ),
            split_char=split_char,
            join_char=" | ",
        )

        assert chunk_processor._split_char == split_char
        assert chunk_processor._join_char == " | "


@patch("engine.prometheus_metric.get_tracing_span")
@patch("engine.prometheus_metric.agent_calls")
def test_empty_input_handling(mock_agent_calls, mock_get_tracing_span, simple_graph_runner, mock_trace_manager):
    """Test handling of empty input."""
    mock_get_tracing_span.return_value = MagicMock()
    chunk_processor = ChunkProcessor(
        trace_manager=mock_trace_manager,
        graph_runner=simple_graph_runner,
        component_attributes=ComponentAttributes(
            component_instance_id=uuid.uuid4(),
            component_instance_name="test_empty",
        ),
        split_char=" ",
    )

    # Test with empty input
    input_payload = AgentPayload(messages=[ChatMessage(role="user", content="")])
    result = asyncio.run(chunk_processor.run(input_payload))

    assert isinstance(result, AgentPayload)
    assert result.messages[0].content == ""
