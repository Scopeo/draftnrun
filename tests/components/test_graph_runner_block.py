"""
Test module for GraphRunnerBlock functionality.
Tests the ability to wrap a GraphRunner as an Agent and use it in another GraphRunner.
"""

import asyncio
import uuid
from unittest.mock import MagicMock, patch

import networkx as nx
import pytest

from engine.components.graph_runner_block import DEFAULT_GRAPH_RUNNER_BLOCK_TOOL_DESCRIPTION, GraphRunnerBlock
from engine.components.types import AgentPayload, ChatMessage, ComponentAttributes
from engine.graph_runner.graph_runner import GraphRunner
from tests.mocks.dummy_agent import DummyAgent


@pytest.fixture
def mock_trace_manager():
    """Mock trace manager that returns a context manager."""
    trace_manager = MagicMock()

    # Create a mock context manager for start_span
    mock_span = MagicMock()
    mock_span.__enter__ = MagicMock(return_value=mock_span)
    mock_span.__exit__ = MagicMock(return_value=None)

    trace_manager.start_span.return_value = mock_span
    mock_span.to_json.return_value = '{"context": {"trace_id": "testid"}, "attributes": {}, "parent_id": null}'
    return trace_manager


@pytest.fixture
def simple_graph_runner(mock_trace_manager):
    """Create a simple graph runner with 3 dummy agents in sequence."""
    # Create dummy agents
    agent1 = DummyAgent(mock_trace_manager, "Step1", "a")
    agent2 = DummyAgent(mock_trace_manager, "Step2", "b")
    agent3 = DummyAgent(mock_trace_manager, "Step3", "c")

    # Create graph structure: agent1 -> agent2 -> agent3
    graph = nx.DiGraph()
    graph.add_edge("agent1", "agent2")
    graph.add_edge("agent2", "agent3")

    # Create runnables dict
    runnables = {
        "agent1": agent1,
        "agent2": agent2,
        "agent3": agent3,
    }

    # Start nodes (only agent1)
    start_nodes = ["agent1"]

    return GraphRunner(
        graph=graph,
        runnables=runnables,
        start_nodes=start_nodes,
        trace_manager=mock_trace_manager,
    )


@pytest.fixture
def nested_graph_runner(mock_trace_manager, simple_graph_runner):
    """Create a graph runner that uses the GraphRunnerBlock to wrap another graph runner."""
    # Create a GraphRunnerBlock that wraps the inner graph runner
    graph_runner_block = GraphRunnerBlock(
        trace_manager=mock_trace_manager,
        graph_runner=simple_graph_runner,
        tool_description=DEFAULT_GRAPH_RUNNER_BLOCK_TOOL_DESCRIPTION,
        component_attributes=ComponentAttributes(
            component_instance_id=uuid.uuid4(),
            component_instance_name="wrapped_inner_graph",
        ),
    )

    # Create additional dummy agents for the outer graph
    pre_agent = DummyAgent(mock_trace_manager, "PRE", "pre")
    post_agent = DummyAgent(mock_trace_manager, "POST", "post")

    # Create graph structure: pre_agent -> graph_runner_block -> post_agent
    graph = nx.DiGraph()
    graph.add_edge("pre_agent", "wrapped_graph")
    graph.add_edge("wrapped_graph", "post_agent")

    # Create runnables dict
    runnables = {
        "pre_agent": pre_agent,
        "wrapped_graph": graph_runner_block,  # Using GraphRunnerBlock as a runnable
        "post_agent": post_agent,
    }

    # Start nodes (only pre_agent)
    start_nodes = ["pre_agent"]

    return GraphRunner(
        graph=graph,
        runnables=runnables,
        start_nodes=start_nodes,
        trace_manager=mock_trace_manager,
    )


@patch("engine.prometheus_metric.get_tracing_span")
@patch("engine.prometheus_metric.agent_calls")
def test_simple_graph_runner(mock_agent_calls, mock_get_tracing_span, simple_graph_runner):
    """Test that a simple graph runner works as expected."""
    # Setup prometheus mocks
    mock_get_tracing_span.return_value = MagicMock(project_id="test_project")
    mock_agent_calls.labels.return_value.inc = MagicMock()

    input_payload = AgentPayload(messages=[ChatMessage(role="user", content="Hello World!")])

    result = asyncio.run(simple_graph_runner.run(input_payload))

    # Should apply Step1, Step2, Step3 prefixes in sequence
    expected = "[Step3] [Step2] [Step1] Hello World!"
    assert result.messages[-1].content == expected


@patch("engine.prometheus_metric.get_tracing_span")
@patch("engine.prometheus_metric.agent_calls")
def test_graph_runner_block_direct(mock_agent_calls, mock_get_tracing_span, mock_trace_manager, simple_graph_runner):
    """Test GraphRunnerBlock directly as an agent."""
    # Setup prometheus mocks
    mock_get_tracing_span.return_value = MagicMock(project_id="test_project")
    mock_agent_calls.labels.return_value.inc = MagicMock()

    # Create GraphRunnerBlock
    graph_runner_block = GraphRunnerBlock(
        trace_manager=mock_trace_manager,
        graph_runner=simple_graph_runner,
        tool_description=DEFAULT_GRAPH_RUNNER_BLOCK_TOOL_DESCRIPTION,
        component_attributes=ComponentAttributes(
            component_instance_id=uuid.uuid4(),
            component_instance_name="direct_test",
        ),
    )

    input_payload = AgentPayload(messages=[ChatMessage(role="user", content="Direct test!")])

    result = asyncio.run(graph_runner_block.run(input_payload))

    # Should apply Step1, Step2, Step3 prefixes in sequence
    expected = "[Step3] [Step2] [Step1] Direct test!"
    assert result.messages[-1].content == expected


@patch("engine.prometheus_metric.get_tracing_span")
@patch("engine.prometheus_metric.agent_calls")
def test_nested_graph_runner(mock_agent_calls, mock_get_tracing_span, nested_graph_runner):
    """Test the key functionality: a GraphRunner that contains a GraphRunnerBlock wrapping another GraphRunner."""
    # Setup prometheus mocks
    mock_get_tracing_span.return_value = MagicMock(project_id="test_project")
    mock_agent_calls.labels.return_value.inc = MagicMock()

    input_payload = AgentPayload(messages=[ChatMessage(role="user", content="Nested test!")])

    result = asyncio.run(nested_graph_runner.run(input_payload))

    # Should apply PRE, then the inner graph (Step1->Step2->Step3), then POST
    expected = "[POST] [Step3] [Step2] [Step1] [PRE] Nested test!"
    assert result.messages[-1].content == expected


@patch("engine.prometheus_metric.get_tracing_span")
@patch("engine.prometheus_metric.agent_calls")
def test_graph_runner_block_tool_description(
    mock_agent_calls, mock_get_tracing_span, mock_trace_manager, simple_graph_runner
):
    """Test that GraphRunnerBlock has the correct tool description."""
    # Setup prometheus mocks
    mock_get_tracing_span.return_value = MagicMock(project_id="test_project")
    mock_agent_calls.labels.return_value.inc = MagicMock()

    graph_runner_block = GraphRunnerBlock(
        trace_manager=mock_trace_manager,
        graph_runner=simple_graph_runner,
        tool_description=DEFAULT_GRAPH_RUNNER_BLOCK_TOOL_DESCRIPTION,
        component_attributes=ComponentAttributes(
            component_instance_id=uuid.uuid4(),
            component_instance_name="test_tool_desc",
        ),
    )

    assert graph_runner_block.tool_description.name == "Graph Runner"
    assert graph_runner_block.tool_description.description == "Execute a graph workflow"


@patch("engine.prometheus_metric.get_tracing_span")
@patch("engine.prometheus_metric.agent_calls")
def test_graph_runner_block_empty_input(
    mock_agent_calls, mock_get_tracing_span, mock_trace_manager, simple_graph_runner
):
    """Test GraphRunnerBlock with empty input."""
    # Setup prometheus mocks
    mock_get_tracing_span.return_value = MagicMock(project_id="test_project")
    mock_agent_calls.labels.return_value.inc = MagicMock()

    graph_runner_block = GraphRunnerBlock(
        trace_manager=mock_trace_manager,
        graph_runner=simple_graph_runner,
        tool_description=DEFAULT_GRAPH_RUNNER_BLOCK_TOOL_DESCRIPTION,
        component_attributes=ComponentAttributes(
            component_instance_id=uuid.uuid4(),
            component_instance_name="empty_test",
        ),
    )

    input_payload = AgentPayload(messages=[])

    result = asyncio.run(graph_runner_block.run(input_payload))

    # Should apply Step1, Step2, Step3 prefixes to "empty input"
    expected = "[Step3] [Step2] [Step1] empty input"
    assert result.messages[-1].content == expected
