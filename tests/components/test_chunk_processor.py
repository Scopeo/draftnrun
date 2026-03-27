"""
Test module for ChunkProcessor functionality.
Tests the ability to split input data, process each chunk with a graph runner, and merge results.
"""

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import networkx as nx
import pytest

from engine.components.chunk_processor import (
    DEFAULT_CHUNK_PROCESSOR_TOOL_DESCRIPTION,
    ChunkProcessor,
    ChunkProcessorInputs,
    ChunkProcessorOutputs,
)
from engine.components.types import AgentPayload, ChatMessage, ComponentAttributes, NodeData
from engine.graph_runner.graph_runner import GraphRunner
from tests.mocks.dummy_agent import DummyAgent


@pytest.fixture
def mock_trace_manager():
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
    """Test the _split method splits input strings correctly."""
    chunk_processor = ChunkProcessor(
        trace_manager=MagicMock(),
        graph_runner=MagicMock(),
        component_attributes=ComponentAttributes(
            component_instance_id=uuid.uuid4(),
            component_instance_name="test",
        ),
        split_char=" ",
    )

    chunks = chunk_processor._split("word1 word2 word3")
    assert chunks == ["word1", "word2", "word3"]

    chunks = chunk_processor._split("word1  word2")
    assert chunks == ["word1", "word2"]

    chunks = chunk_processor._split("")
    assert chunks == []


def test_merge_method():
    """Test the _merge method combines string results correctly."""
    chunk_processor = ChunkProcessor(
        trace_manager=MagicMock(),
        graph_runner=MagicMock(),
        component_attributes=ComponentAttributes(
            component_instance_id=uuid.uuid4(),
            component_instance_name="test",
        ),
        join_char=" | ",
    )

    merged = chunk_processor._merge(["result1", "result2", "result3"])
    assert merged == "result1 | result2 | result3"

    merged = chunk_processor._merge([])
    assert merged == ""


@patch("engine.prometheus_metric.get_tracing_span")
@patch("engine.prometheus_metric.agent_calls")
def test_chunk_processor_end_to_end(mock_agent_calls, mock_get_tracing_span, simple_graph_runner, mock_trace_manager):
    """Test the complete chunk processor workflow via legacy AgentPayload caller path."""
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

    input_payload = AgentPayload(messages=[ChatMessage(role="user", content="hello world")])
    result = asyncio.run(chunk_processor.run(input_payload))

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
    """Test handling of empty input via legacy AgentPayload caller path."""
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

    input_payload = AgentPayload(messages=[ChatMessage(role="user", content="")])
    result = asyncio.run(chunk_processor.run(input_payload))

    assert isinstance(result, AgentPayload)
    assert result.messages[0].content == ""


def test_chunk_processor_migrated_flag_and_schemas():
    """Verify typed I/O contract: migrated flag, schemas, and canonical ports."""
    assert ChunkProcessor.migrated is True
    assert ChunkProcessor.get_inputs_schema() is ChunkProcessorInputs
    assert ChunkProcessor.get_outputs_schema() is ChunkProcessorOutputs
    assert ChunkProcessor.get_canonical_ports() == {"input": "input", "output": "output"}


@patch("engine.prometheus_metric.get_tracing_span")
@patch("engine.prometheus_metric.agent_calls")
def test_chunk_processor_node_data_path(
    mock_agent_calls, mock_get_tracing_span, mock_trace_manager, simple_graph_runner
):
    """Test primary migrated path: run(NodeData) returns NodeData with output field."""
    mock_get_tracing_span.return_value = MagicMock(project_id="test_project")
    mock_agent_calls.labels.return_value.inc = MagicMock()

    chunk_processor = ChunkProcessor(
        trace_manager=mock_trace_manager,
        graph_runner=simple_graph_runner,
        component_attributes=ComponentAttributes(
            component_instance_id=uuid.uuid4(),
            component_instance_name="node_data_test",
        ),
        split_char=" ",
        join_char=" || ",
    )

    input_node_data = NodeData(data={"input": "hello world"}, ctx={})
    result = asyncio.run(chunk_processor.run(input_node_data))

    assert isinstance(result, NodeData)
    assert "[PROCESSED]" in result.data["output"]
    assert " || " in result.data["output"]


@patch("engine.prometheus_metric.get_tracing_span")
@patch("engine.prometheus_metric.agent_calls")
def test_chunk_processor_node_data_empty_input(
    mock_agent_calls, mock_get_tracing_span, mock_trace_manager, simple_graph_runner
):
    """Test NodeData path with empty input returns empty output."""
    mock_get_tracing_span.return_value = MagicMock(project_id="test_project")
    mock_agent_calls.labels.return_value.inc = MagicMock()

    chunk_processor = ChunkProcessor(
        trace_manager=mock_trace_manager,
        graph_runner=simple_graph_runner,
        component_attributes=ComponentAttributes(
            component_instance_id=uuid.uuid4(),
            component_instance_name="node_data_empty_test",
        ),
        split_char=" ",
    )

    input_node_data = NodeData(data={}, ctx={})
    result = asyncio.run(chunk_processor.run(input_node_data))

    assert isinstance(result, NodeData)
    assert result.data["output"] == ""


def test_chunk_processor_extracts_content_from_messages_list(mock_trace_manager):
    """When input is a messages list (from Start node auto-wire), extract last message content
    as the string to split. This is a temporary bridge until port mappings are removed."""
    captured_calls = []

    async def fake_run(data):
        captured_calls.append(data)
        return AgentPayload(messages=[ChatMessage(role="assistant", content=f"processed: {data['input']}")])

    mock_graph_runner = MagicMock()
    mock_graph_runner.run = fake_run
    mock_graph_runner.reset = MagicMock()

    chunk_processor = ChunkProcessor(
        trace_manager=mock_trace_manager,
        graph_runner=mock_graph_runner,
        component_attributes=ComponentAttributes(
            component_instance_id=uuid.uuid4(),
            component_instance_name="messages_list_test",
        ),
        split_char=" ",
        join_char=", ",
    )

    messages_input = [{"role": "user", "content": "hello world"}]
    inputs = ChunkProcessorInputs(input=messages_input)
    result = asyncio.run(chunk_processor._run_without_io_trace(inputs, ctx={}))

    assert len(captured_calls) == 2
    assert result.output == "processed: hello, processed: world"


def test_chunk_processor_injects_messages_for_chunks(mock_trace_manager):
    """Each chunk must have messages injected so inner Agent projects can consume it."""
    captured_calls = []

    async def fake_run(data):
        captured_calls.append(data)
        return AgentPayload(messages=[ChatMessage(role="assistant", content=f"processed: {data['input']}")])

    mock_graph_runner = MagicMock()
    mock_graph_runner.run = fake_run
    mock_graph_runner.reset = MagicMock()

    chunk_processor = ChunkProcessor(
        trace_manager=mock_trace_manager,
        graph_runner=mock_graph_runner,
        component_attributes=ComponentAttributes(
            component_instance_id=uuid.uuid4(),
            component_instance_name="inject_test",
        ),
        split_char=" ",
        join_char=", ",
    )

    inputs = ChunkProcessorInputs(input="hello world")
    result = asyncio.run(chunk_processor._run_without_io_trace(inputs, ctx={}))

    assert len(captured_calls) == 2
    assert captured_calls[0]["messages"] == [{"role": "user", "content": "hello"}]
    assert captured_calls[1]["messages"] == [{"role": "user", "content": "world"}]
    assert result.output == "processed: hello, processed: world"
