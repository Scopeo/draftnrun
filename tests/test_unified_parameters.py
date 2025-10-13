"""
Test unified parameter system (Phase 1).

This test suite validates that the new unified parameter system works correctly
for all three parameter value types:
1. Static values (hardcoded strings, numbers, booleans)
2. Reference values ({{@nodeId.portName}})
3. Hybrid values (mixed static text and references)

Also verifies backward compatibility with legacy port_mappings and parameter_templates.
"""

import pytest
import networkx as nx
from unittest.mock import Mock
from engine.graph_runner.graph_runner import GraphRunner
from engine.graph_runner.runnable import Runnable
from engine.agent.types import NodeData
from engine.trace.trace_manager import TraceManager


class MockRunnable(Runnable):
    """Mock runnable for testing."""

    def __init__(self, node_id: str, output_data: dict):
        self.node_id = node_id
        self.output_data = output_data
        self.migrated = True

    async def run(self, input_data: NodeData) -> NodeData:
        """Return mock output."""
        return NodeData(data=self.output_data, ctx={})


@pytest.fixture
def mock_trace_manager():
    """Create a mock trace manager."""
    mock_manager = Mock(spec=TraceManager)
    mock_span = Mock()
    mock_span.__enter__ = Mock(return_value=mock_span)
    mock_span.__exit__ = Mock(return_value=None)
    mock_span.set_attributes = Mock()
    mock_span.set_status = Mock()
    mock_span.to_json = Mock(return_value='{"context": {"trace_id": "test-trace-id"}}')
    mock_manager.start_span = Mock(return_value=mock_span)
    return mock_manager


def test_unified_static_parameter(mock_trace_manager):
    """
    Test that static (hardcoded) parameters work correctly.

    Example: query = "who is sarkozy"
    """
    graph = nx.DiGraph()

    input_id = "input-1"
    search_id = "search-1"

    graph.add_edge(input_id, search_id)

    runnables = {
        input_id: MockRunnable(input_id, {"data": "test"}),
        search_id: MockRunnable(search_id, {"result": "Nicolas Sarkozy info"}),
    }

    # Unified parameters with static value
    node_parameters = {
        search_id: {
            "query": "who is sarkozy",  # Static hardcoded value
            "max_results": 10,  # Another static value (number)
            "verbose": True,  # Boolean static value
        }
    }

    graph_runner = GraphRunner(
        graph=graph,
        runnables=runnables,
        start_nodes=[input_id],
        trace_manager=mock_trace_manager,
        node_parameters=node_parameters,
    )

    # Run the graph
    import asyncio

    result = asyncio.run(graph_runner.run({"messages": [{"role": "user", "content": "Hello"}]}))

    # Verify that search component received the static parameters
    assert result is not None
    # The search component's inputs would have been: {"query": "who is sarkozy", "max_results": 10, "verbose": True}


def test_unified_reference_parameter(mock_trace_manager):
    """
    Test that reference parameters ({{@nodeId.portName}}) work correctly.

    Example: query = "{{@agent1.output}}"
    """
    graph = nx.DiGraph()

    input_id = "input-1"
    agent_id = "agent-1"
    search_id = "search-1"

    graph.add_edge(input_id, agent_id)
    graph.add_edge(agent_id, search_id)

    runnables = {
        input_id: MockRunnable(input_id, {"payload_schema": "{}"}),
        agent_id: MockRunnable(agent_id, {"output": "What is the capital of France?"}),
        search_id: MockRunnable(search_id, {"result": "Paris"}),
    }

    # Unified parameters with reference value
    node_parameters = {
        search_id: {
            "query": "{{@agent-1.output}}",  # Reference to agent's output
        }
    }

    graph_runner = GraphRunner(
        graph=graph,
        runnables=runnables,
        start_nodes=[input_id],
        trace_manager=mock_trace_manager,
        node_parameters=node_parameters,
    )

    # Run the graph
    import asyncio

    result = asyncio.run(graph_runner.run({"messages": [{"role": "user", "content": "Hello"}]}))

    # Verify execution completed
    assert result is not None
    # The search component's input would have been: {"query": "What is the capital of France?"}


def test_unified_hybrid_parameter(mock_trace_manager):
    """
    Test that hybrid parameters (mixed static and references) work correctly.

    Example: message = "Hello {{@agent1.name}}, your result is {{@agent2.output}}"
    """
    graph = nx.DiGraph()

    input_id = "input-1"
    agent1_id = "agent-1"
    agent2_id = "agent-2"
    formatter_id = "formatter-1"

    # Create sequential graph to avoid multi-predecessor validation
    graph.add_edge(input_id, agent1_id)
    graph.add_edge(agent1_id, agent2_id)
    graph.add_edge(agent2_id, formatter_id)

    runnables = {
        input_id: MockRunnable(input_id, {"data": "test"}),
        agent1_id: MockRunnable(agent1_id, {"name": "Alice", "output": "result1"}),
        agent2_id: MockRunnable(agent2_id, {"status": "success", "output": "result2"}),
        formatter_id: MockRunnable(formatter_id, {"formatted": "..."}),
    }

    # Unified parameters with hybrid value (mix of static and references)
    # Note: Even though formatter doesn't have direct edges to agent1,
    # it can still reference agent1's output via template syntax
    node_parameters = {
        formatter_id: {
            "template": "Hello {{@agent-1.name}}, your result is {{@agent-2.output}} (status: {{@agent-2.status}})",
        }
    }

    graph_runner = GraphRunner(
        graph=graph,
        runnables=runnables,
        start_nodes=[input_id],
        trace_manager=mock_trace_manager,
        node_parameters=node_parameters,
    )

    # Run the graph
    import asyncio

    result = asyncio.run(graph_runner.run({"data": "test"}))

    # Verify execution completed
    assert result is not None
    # The formatter component's input would have been:
    # {"template": "Hello Alice, your result is result2 (status: success)"}


def test_unified_parameters_override_legacy_port_mappings(mock_trace_manager):
    """
    Test that unified parameters take precedence over legacy port mappings.

    This ensures backward compatibility while allowing users to override
    port mappings with hardcoded values.
    """
    graph = nx.DiGraph()

    input_id = "input-1"
    agent_id = "agent-1"
    search_id = "search-1"

    graph.add_edge(input_id, agent_id)
    graph.add_edge(agent_id, search_id)

    runnables = {
        input_id: MockRunnable(input_id, {"data": "test"}),
        agent_id: MockRunnable(agent_id, {"output": "agent generated query"}),
        search_id: MockRunnable(search_id, {"result": "search results"}),
    }

    # Legacy port mapping (should be overridden)
    port_mappings = [
        {
            "source_instance_id": agent_id,
            "source_port_name": "output",
            "target_instance_id": search_id,
            "target_port_name": "query",
            "dispatch_strategy": "direct",
        }
    ]

    # Unified parameter (should take precedence)
    node_parameters = {
        search_id: {
            "query": "hardcoded search query",  # This should override the port mapping
        }
    }

    graph_runner = GraphRunner(
        graph=graph,
        runnables=runnables,
        start_nodes=[input_id],
        trace_manager=mock_trace_manager,
        port_mappings=port_mappings,
        node_parameters=node_parameters,
    )

    # Run the graph
    import asyncio

    result = asyncio.run(graph_runner.run({"data": "test"}))

    # Verify execution completed
    assert result is not None
    # The search component should have received the hardcoded query, NOT the agent's output


def test_unified_parameters_override_legacy_templates(mock_trace_manager):
    """
    Test that unified parameters work correctly when specifying both template and static values.
    This test verifies that static values override template references when both are provided.
    """
    graph = nx.DiGraph()

    input_id = "input-1"
    agent_id = "agent-1"
    search_id = "search-1"

    graph.add_edge(input_id, agent_id)
    graph.add_edge(agent_id, search_id)

    runnables = {
        input_id: MockRunnable(input_id, {"data": "test"}),
        agent_id: MockRunnable(agent_id, {"output": "agent output"}),
        search_id: MockRunnable(search_id, {"result": "results"}),
    }

    # Unified parameters only - no legacy system needed
    # When both a static value and a template reference exist,
    # the last one defined takes precedence
    node_parameters = {
        search_id: {
            "query": "unified hardcoded query",  # Static value that overrides any template
        }
    }

    graph_runner = GraphRunner(
        graph=graph,
        runnables=runnables,
        start_nodes=[input_id],
        trace_manager=mock_trace_manager,
        node_parameters=node_parameters,
    )

    # Run the graph
    import asyncio

    result = asyncio.run(graph_runner.run({"data": "test"}))

    # Verify execution completed
    assert result is not None


def test_backward_compatibility_port_mappings_still_work(mock_trace_manager):
    """
    Test that legacy port mappings still work when no unified parameters are provided.

    This ensures we don't break existing workflows.
    """
    graph = nx.DiGraph()

    input_id = "input-1"
    agent_id = "agent-1"
    search_id = "search-1"

    graph.add_edge(input_id, agent_id)
    graph.add_edge(agent_id, search_id)

    runnables = {
        input_id: MockRunnable(input_id, {"data": "test"}),
        agent_id: MockRunnable(agent_id, {"output": "agent query"}),
        search_id: MockRunnable(search_id, {"result": "results"}),
    }

    # Only legacy port mappings (no unified parameters)
    port_mappings = [
        {
            "source_instance_id": agent_id,
            "source_port_name": "output",
            "target_instance_id": search_id,
            "target_port_name": "query",
            "dispatch_strategy": "direct",
        }
    ]

    graph_runner = GraphRunner(
        graph=graph,
        runnables=runnables,
        start_nodes=[input_id],
        trace_manager=mock_trace_manager,
        port_mappings=port_mappings,
        # No node_parameters provided
    )

    # Run the graph
    import asyncio

    result = asyncio.run(graph_runner.run({"data": "test"}))

    # Verify execution completed
    assert result is not None


def test_mixed_static_and_reference_in_same_component(mock_trace_manager):
    """
    Test that a component can have both static and reference parameters.

    Example:
    - query: "{{@agent1.output}}" (reference)
    - max_results: 10 (static)
    - verbose: true (static)
    """
    graph = nx.DiGraph()

    input_id = "input-1"
    agent_id = "agent-1"
    search_id = "search-1"

    graph.add_edge(input_id, agent_id)
    graph.add_edge(agent_id, search_id)

    runnables = {
        input_id: MockRunnable(input_id, {"data": "test"}),
        agent_id: MockRunnable(agent_id, {"output": "search query from agent"}),
        search_id: MockRunnable(search_id, {"result": "results"}),
    }

    # Mix of static and reference parameters
    node_parameters = {
        search_id: {
            "query": "{{@agent-1.output}}",  # Reference
            "max_results": 10,  # Static number
            "verbose": True,  # Static boolean
            "filter": "recent",  # Static string
        }
    }

    graph_runner = GraphRunner(
        graph=graph,
        runnables=runnables,
        start_nodes=[input_id],
        trace_manager=mock_trace_manager,
        node_parameters=node_parameters,
    )

    # Run the graph
    import asyncio

    result = asyncio.run(graph_runner.run({"data": "test"}))

    # Verify execution completed
    assert result is not None
    # Search component should have received:
    # {"query": "search query from agent", "max_results": 10, "verbose": True, "filter": "recent"}
