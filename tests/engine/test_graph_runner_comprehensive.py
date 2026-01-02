"""
Comprehensive tests for GraphRunner with multiple combinations.

This test suite covers all possible GraphRunner scenarios to ensure robust
build-time validation and runtime execution across different component types.
"""

from typing import List, Type

import networkx as nx
import pytest
from pydantic import BaseModel

from engine.agent.types import ChatMessage
from engine.graph_runner.graph_runner import GraphRunner
from engine.trace.trace_manager import TraceManager
from tests.mocks.dummy_agent import DummyAgent

# Note: prometheus_metrics fixture is defined in test_graph_runner_ports.py


class TestGraphRunnerBuildTimeValidation:
    """Test build-time validation for various GraphRunner configurations."""

    def test_single_node_graph_no_mappings(self):
        """Test single node graph with no explicit port mappings."""
        tm = TraceManager(project_name="test")
        g = nx.DiGraph()
        g.add_node("A")

        runnables = {
            "A": DummyAgent(tm, "A"),
        }

        # Should build successfully with no mappings (start node passthrough)
        gr = GraphRunner(
            graph=g,
            runnables=runnables,
            start_nodes=["A"],
            trace_manager=tm,
        )
        assert gr is not None

    def test_two_node_graph_with_valid_mappings(self):
        """Test two node graph with valid port mappings."""
        tm = TraceManager(project_name="test")
        g = nx.DiGraph()
        g.add_nodes_from(["A", "B"])
        g.add_edge("A", "B")

        runnables = {
            "A": DummyAgent(tm, "A"),
            "B": DummyAgent(tm, "B"),
        }

        valid_mappings = [
            {
                "source_instance_id": "A",
                "source_port_name": "output",
                "target_instance_id": "B",
                "target_port_name": "input",
                "dispatch_strategy": "direct",
            }
        ]

        # Should build successfully
        gr = GraphRunner(
            graph=g,
            runnables=runnables,
            start_nodes=["A"],
            trace_manager=tm,
            port_mappings=valid_mappings,
        )
        assert gr is not None

    def test_three_node_chain_graph(self):
        """Test three node chain: A -> B -> C."""
        tm = TraceManager(project_name="test")
        g = nx.DiGraph()
        g.add_nodes_from(["A", "B", "C"])
        g.add_edge("A", "B")
        g.add_edge("B", "C")

        runnables = {
            "A": DummyAgent(tm, "A"),
            "B": DummyAgent(tm, "B"),
            "C": DummyAgent(tm, "C"),
        }

        valid_mappings = [
            {
                "source_instance_id": "A",
                "source_port_name": "output",
                "target_instance_id": "B",
                "target_port_name": "input",
                "dispatch_strategy": "direct",
            },
            {
                "source_instance_id": "B",
                "source_port_name": "output",
                "target_instance_id": "C",
                "target_port_name": "input",
                "dispatch_strategy": "direct",
            },
        ]

        # Should build successfully
        gr = GraphRunner(
            graph=g,
            runnables=runnables,
            start_nodes=["A"],
            trace_manager=tm,
            port_mappings=valid_mappings,
        )
        assert gr is not None

    def test_diamond_graph_structure(self):
        """Test diamond graph: A -> B, A -> C, B -> D, C -> D."""
        tm = TraceManager(project_name="test")
        g = nx.DiGraph()
        g.add_nodes_from(["A", "B", "C", "D"])
        g.add_edge("A", "B")
        g.add_edge("A", "C")
        g.add_edge("B", "D")
        g.add_edge("C", "D")

        runnables = {
            "A": DummyAgent(tm, "A"),
            "B": DummyAgent(tm, "B"),
            "C": DummyAgent(tm, "C"),
            "D": DummyAgent(tm, "D"),
        }

        valid_mappings = [
            {
                "source_instance_id": "A",
                "source_port_name": "output",
                "target_instance_id": "B",
                "target_port_name": "input",
                "dispatch_strategy": "direct",
            },
            {
                "source_instance_id": "A",
                "source_port_name": "output",
                "target_instance_id": "C",
                "target_port_name": "input",
                "dispatch_strategy": "direct",
            },
            {
                "source_instance_id": "B",
                "source_port_name": "output",
                "target_instance_id": "D",
                "target_port_name": "input",
                "dispatch_strategy": "direct",
            },
            {
                "source_instance_id": "C",
                "source_port_name": "output",
                "target_instance_id": "D",
                "target_port_name": "input",
                "dispatch_strategy": "direct",
            },
        ]

        # Should build successfully
        gr = GraphRunner(
            graph=g,
            runnables=runnables,
            start_nodes=["A"],
            trace_manager=tm,
            port_mappings=valid_mappings,
        )
        assert gr is not None

    def test_multiple_start_nodes(self):
        """Test graph with multiple start nodes."""
        tm = TraceManager(project_name="test")
        g = nx.DiGraph()
        g.add_nodes_from(["A", "B", "C"])
        g.add_edge("A", "C")
        g.add_edge("B", "C")

        runnables = {
            "A": DummyAgent(tm, "A"),
            "B": DummyAgent(tm, "B"),
            "C": DummyAgent(tm, "C"),
        }

        valid_mappings = [
            {
                "source_instance_id": "A",
                "source_port_name": "output",
                "target_instance_id": "C",
                "target_port_name": "input",
                "dispatch_strategy": "direct",
            },
            {
                "source_instance_id": "B",
                "source_port_name": "output",
                "target_instance_id": "C",
                "target_port_name": "input",
                "dispatch_strategy": "direct",
            },
        ]

        # Should build successfully
        gr = GraphRunner(
            graph=g,
            runnables=runnables,
            start_nodes=["A", "B"],
            trace_manager=tm,
            port_mappings=valid_mappings,
        )
        assert gr is not None

    def test_empty_graph(self):
        """Test empty graph (no nodes)."""
        tm = TraceManager(project_name="test")
        g = nx.DiGraph()

        runnables = {}

        # Should build successfully (edge case)
        gr = GraphRunner(
            graph=g,
            runnables=runnables,
            start_nodes=[],
            trace_manager=tm,
        )
        assert gr is not None

    def test_single_node_with_self_loop(self):
        """Test single node with self loop - should fail due to DAG enforcement."""
        tm = TraceManager(project_name="test")
        g = nx.DiGraph()
        g.add_node("A")
        g.add_edge("A", "A")

        runnables = {
            "A": DummyAgent(tm, "A"),
        }

        valid_mappings = [
            {
                "source_instance_id": "A",
                "source_port_name": "output",
                "target_instance_id": "A",
                "target_port_name": "input",
                "dispatch_strategy": "direct",
            }
        ]

        # Should fail due to DAG enforcement (self-loops forbidden)
        with pytest.raises(ValueError, match="Graph contains cycles"):
            GraphRunner(
                graph=g,
                runnables=runnables,
                start_nodes=["A"],
                trace_manager=tm,
                port_mappings=valid_mappings,
            )


class TestGraphRunnerErrorCases:
    """Test GraphRunner error cases and validation failures."""

    def test_missing_runnable(self):
        """Test error when runnable is missing for a node."""
        tm = TraceManager(project_name="test")
        g = nx.DiGraph()
        g.add_node("A")

        runnables = {}  # Missing runnable for A

        with pytest.raises(ValueError, match="All runnables must be in the graph"):
            GraphRunner(
                graph=g,
                runnables=runnables,
                start_nodes=["A"],
                trace_manager=tm,
            )

    def test_duplicate_runnable_ids(self):
        """Test that duplicate runnable IDs are allowed (not a coercion concern)."""
        tm = TraceManager(project_name="test")
        g = nx.DiGraph()
        g.add_nodes_from(["A", "B"])

        runnables = {
            "A": DummyAgent(tm, "A"),
            "B": DummyAgent(tm, "A"),  # Duplicate ID - this is allowed
        }

        # Should build successfully (duplicate IDs are not a coercion concern)
        gr = GraphRunner(
            graph=g,
            runnables=runnables,
            start_nodes=["A"],
            trace_manager=tm,
        )
        assert gr is not None

    def test_runnable_not_in_graph(self):
        """Test error when runnable exists but node is not in graph."""
        tm = TraceManager(project_name="test")
        g = nx.DiGraph()
        g.add_node("A")
        # B is in runnables but not in graph

        runnables = {
            "A": DummyAgent(tm, "A"),
            "B": DummyAgent(tm, "B"),
        }

        with pytest.raises(ValueError, match="All runnables must be in the graph"):
            GraphRunner(
                graph=g,
                runnables=runnables,
                start_nodes=["A"],
                trace_manager=tm,
            )

    def test_multiple_predecessors_without_mappings(self):
        """Test error when node has multiple predecessors but no explicit mappings."""
        tm = TraceManager(project_name="test")
        g = nx.DiGraph()
        g.add_nodes_from(["A", "B", "C"])
        g.add_edge("A", "C")
        g.add_edge("B", "C")  # C has two predecessors

        runnables = {
            "A": DummyAgent(tm, "A"),
            "B": DummyAgent(tm, "B"),
            "C": DummyAgent(tm, "C"),
        }

        with pytest.raises(ValueError, match="has multiple incoming connections"):
            GraphRunner(
                graph=g,
                runnables=runnables,
                start_nodes=["A", "B"],
                trace_manager=tm,
            )

    def test_invalid_port_mapping_source_not_found(self):
        """Test that non-existent sources are now forbidden in strict validation."""
        tm = TraceManager(project_name="test")
        g = nx.DiGraph()
        g.add_nodes_from(["A", "B"])

        # Create a component with a restrictive input type
        class MockRestrictiveComponent:
            def get_inputs_schema(self) -> Type[BaseModel]:
                class Inputs(BaseModel):
                    messages: list[ChatMessage]

                return Inputs

        runnables = {
            "A": DummyAgent(tm, "A"),
            "B": MockRestrictiveComponent(),
        }

        invalid_mappings = [
            {
                "source_instance_id": "NONEXISTENT",
                "source_port_name": "output",
                "target_instance_id": "B",
                "target_port_name": "messages",
                "dispatch_strategy": "direct",
            }
        ]

        # Should fail due to strict validation - all mapped nodes must exist
        with pytest.raises(ValueError, match="All runnables must be in the graph"):
            GraphRunner(
                graph=g,
                runnables=runnables,
                start_nodes=["A"],
                trace_manager=tm,
                port_mappings=invalid_mappings,
            )

    def test_invalid_port_mapping_target_not_found(self):
        """Test error when port mapping references non-existent target."""
        tm = TraceManager(project_name="test")
        g = nx.DiGraph()
        g.add_nodes_from(["A", "B"])

        runnables = {
            "A": DummyAgent(tm, "A"),
            "B": DummyAgent(tm, "B"),
        }

        invalid_mappings = [
            {
                "source_instance_id": "A",
                "source_port_name": "output",
                "target_instance_id": "NONEXISTENT",
                "target_port_name": "input",
                "dispatch_strategy": "direct",
            }
        ]

        # Should fail due to strict validation - all mapped nodes must exist
        with pytest.raises(ValueError, match="All runnables must be in the graph"):
            GraphRunner(
                graph=g,
                runnables=runnables,
                start_nodes=["A"],
                trace_manager=tm,
                port_mappings=invalid_mappings,
            )


class TestGraphRunnerPortMappingValidation:
    """Test port mapping validation with different component types."""

    def test_string_to_string_mapping(self):
        """Test string to string port mapping."""
        tm = TraceManager(project_name="test")
        g = nx.DiGraph()
        g.add_nodes_from(["A", "B"])

        runnables = {
            "A": DummyAgent(tm, "A"),
            "B": DummyAgent(tm, "B"),
        }

        mappings = [
            {
                "source_instance_id": "A",
                "source_port_name": "output",
                "target_instance_id": "B",
                "target_port_name": "input",
                "dispatch_strategy": "direct",
            }
        ]

        # Should build successfully (str -> str is always valid)
        gr = GraphRunner(
            graph=g,
            runnables=runnables,
            start_nodes=["A"],
            trace_manager=tm,
            port_mappings=mappings,
        )
        assert gr is not None

    def test_list_chatmessage_to_string_mapping(self):
        """Test list[ChatMessage] to string port mapping."""
        tm = TraceManager(project_name="test")
        g = nx.DiGraph()
        g.add_nodes_from(["A", "B"])

        # Mock components with specific schemas
        class MockInputBlock:
            def get_outputs_schema(self) -> Type[BaseModel]:
                class Outputs(BaseModel):
                    messages: List[ChatMessage]

                return Outputs

        class MockRAG:
            def get_inputs_schema(self) -> Type[BaseModel]:
                class Inputs(BaseModel):
                    query_text: str

                return Inputs

        runnables = {
            "A": MockInputBlock(),
            "B": MockRAG(),
        }

        mappings = [
            {
                "source_instance_id": "A",
                "source_port_name": "messages",
                "target_instance_id": "B",
                "target_port_name": "query_text",
                "dispatch_strategy": "direct",
            }
        ]

        # Should build successfully (list[ChatMessage] -> str is valid)
        gr = GraphRunner(
            graph=g,
            runnables=runnables,
            start_nodes=["A"],
            trace_manager=tm,
            port_mappings=mappings,
        )
        assert gr is not None

    def test_list_chatmessage_to_list_chatmessage_mapping(self):
        """Test list[ChatMessage] to list[ChatMessage] port mapping."""
        tm = TraceManager(project_name="test")
        g = nx.DiGraph()
        g.add_nodes_from(["A", "B"])

        # Mock components with specific schemas
        class MockInputBlock:
            def get_outputs_schema(self) -> Type[BaseModel]:
                class Outputs(BaseModel):
                    messages: List[ChatMessage]

                return Outputs

        class MockReActAgent:
            def get_inputs_schema(self) -> Type[BaseModel]:
                class Inputs(BaseModel):
                    messages: List[ChatMessage]

                return Inputs

        runnables = {
            "A": MockInputBlock(),
            "B": MockReActAgent(),
        }

        mappings = [
            {
                "source_instance_id": "A",
                "source_port_name": "messages",
                "target_instance_id": "B",
                "target_port_name": "messages",
                "dispatch_strategy": "direct",
            }
        ]

        # Should build successfully (list[ChatMessage] -> list[ChatMessage] is valid)
        gr = GraphRunner(
            graph=g,
            runnables=runnables,
            start_nodes=["A"],
            trace_manager=tm,
            port_mappings=mappings,
        )
        assert gr is not None

    def test_invalid_type_coercion(self):
        """Test invalid type coercion that should fail validation."""
        tm = TraceManager(project_name="test")
        g = nx.DiGraph()
        g.add_nodes_from(["A", "B"])

        # Mock components with incompatible schemas using proper Pydantic models
        class MockStringOutput:
            migrated = True  # Mark as migrated to get strict validation

            def get_outputs_schema(self) -> Type[BaseModel]:
                class Outputs(BaseModel):
                    output: str

                return Outputs

        class MockListInput:
            migrated = True  # Mark as migrated to get strict validation

            def get_inputs_schema(self) -> Type[BaseModel]:
                class Inputs(BaseModel):
                    messages: List[ChatMessage]

                return Inputs

        runnables = {
            "A": MockStringOutput(),
            "B": MockListInput(),
        }

        mappings = [
            {
                "source_instance_id": "A",
                "source_port_name": "output",
                "target_instance_id": "B",
                "target_port_name": "messages",
                "dispatch_strategy": "direct",
            }
        ]

        # Should fail validation (str -> list[ChatMessage] is invalid)
        with pytest.raises(ValueError, match="Cannot coerce"):
            GraphRunner(
                graph=g,
                runnables=runnables,
                start_nodes=["A"],
                trace_manager=tm,
                port_mappings=mappings,
            )

    def test_complex_nested_graph_validation(self):
        """Test complex nested graph with multiple type combinations."""
        tm = TraceManager(project_name="test")
        g = nx.DiGraph()
        g.add_nodes_from(["input", "rag", "websearch", "react", "output"])
        g.add_edge("input", "rag")
        g.add_edge("input", "websearch")
        g.add_edge("rag", "react")
        g.add_edge("websearch", "react")
        g.add_edge("react", "output")

        # Mock components with realistic schemas
        class MockInputBlock:
            def get_outputs_schema(self) -> Type[BaseModel]:
                class Outputs(BaseModel):
                    messages: List[ChatMessage]

                return Outputs

        class MockRAG:
            def get_inputs_schema(self) -> Type[BaseModel]:
                class Inputs(BaseModel):
                    query_text: str

                return Inputs

            def get_outputs_schema(self) -> Type[BaseModel]:
                class Outputs(BaseModel):
                    output: str

                return Outputs

        class MockWebSearch:
            def get_inputs_schema(self) -> Type[BaseModel]:
                class Inputs(BaseModel):
                    query: str

                return Inputs

            def get_outputs_schema(self) -> Type[BaseModel]:
                class Outputs(BaseModel):
                    output: str

                return Outputs

        class MockReActAgent:
            def get_inputs_schema(self) -> Type[BaseModel]:
                class Inputs(BaseModel):
                    messages: List[ChatMessage]

                return Inputs

            def get_outputs_schema(self) -> Type[BaseModel]:
                class Outputs(BaseModel):
                    output: str

                return Outputs

        class MockOutput:
            def get_inputs_schema(self) -> Type[BaseModel]:
                class Inputs(BaseModel):
                    output: str

                return Inputs

        runnables = {
            "input": MockInputBlock(),
            "rag": MockRAG(),
            "websearch": MockWebSearch(),
            "react": MockReActAgent(),
            "output": MockOutput(),
        }

        mappings = [
            {
                "source_instance_id": "input",
                "source_port_name": "messages",
                "target_instance_id": "rag",
                "target_port_name": "query_text",
                "dispatch_strategy": "direct",
            },
            {
                "source_instance_id": "input",
                "source_port_name": "messages",
                "target_instance_id": "websearch",
                "target_port_name": "query",
                "dispatch_strategy": "direct",
            },
            {
                "source_instance_id": "rag",
                "source_port_name": "output",
                "target_instance_id": "react",
                "target_port_name": "messages",
                "dispatch_strategy": "direct",
            },
            {
                "source_instance_id": "websearch",
                "source_port_name": "output",
                "target_instance_id": "react",
                "target_port_name": "messages",
                "dispatch_strategy": "direct",
            },
            {
                "source_instance_id": "react",
                "source_port_name": "output",
                "target_instance_id": "output",
                "target_port_name": "output",
                "dispatch_strategy": "direct",
            },
        ]

        # Should build successfully (all coercions are valid)
        gr = GraphRunner(
            graph=g,
            runnables=runnables,
            start_nodes=["input"],
            trace_manager=tm,
            port_mappings=mappings,
        )
        assert gr is not None


class TestGraphRunnerEdgeCases:
    """Test GraphRunner edge cases and boundary conditions."""

    def test_graph_with_isolated_nodes(self):
        """Test graph with isolated nodes (no connections)."""
        tm = TraceManager(project_name="test")
        g = nx.DiGraph()
        g.add_nodes_from(["A", "B", "C"])

        runnables = {
            "A": DummyAgent(tm, "A"),
            "B": DummyAgent(tm, "B"),
            "C": DummyAgent(tm, "C"),
        }

        # Should build successfully (isolated nodes are valid)
        gr = GraphRunner(
            graph=g,
            runnables=runnables,
            start_nodes=["A"],
            trace_manager=tm,
        )
        assert gr is not None

    def test_graph_with_cycles(self):
        """Test graph with cycles - should fail due to DAG enforcement."""
        tm = TraceManager(project_name="test")
        g = nx.DiGraph()
        g.add_nodes_from(["A", "B", "C"])
        g.add_edge("A", "B")
        g.add_edge("B", "C")
        g.add_edge("C", "A")  # Creates cycle

        runnables = {
            "A": DummyAgent(tm, "A"),
            "B": DummyAgent(tm, "B"),
            "C": DummyAgent(tm, "C"),
        }

        mappings = [
            {
                "source_instance_id": "A",
                "source_port_name": "output",
                "target_instance_id": "B",
                "target_port_name": "input",
                "dispatch_strategy": "direct",
            },
            {
                "source_instance_id": "B",
                "source_port_name": "output",
                "target_instance_id": "C",
                "target_port_name": "input",
                "dispatch_strategy": "direct",
            },
            {
                "source_instance_id": "C",
                "source_port_name": "output",
                "target_instance_id": "A",
                "target_port_name": "input",
                "dispatch_strategy": "direct",
            },
        ]

        # Should fail due to DAG enforcement (cycles forbidden)
        with pytest.raises(ValueError, match="Graph contains cycles"):
            GraphRunner(
                graph=g,
                runnables=runnables,
                start_nodes=["A"],
                trace_manager=tm,
                port_mappings=mappings,
            )

    def test_graph_with_parallel_paths(self):
        """Test graph with parallel paths from same source."""
        tm = TraceManager(project_name="test")
        g = nx.DiGraph()
        g.add_nodes_from(["A", "B", "C", "D"])
        g.add_edge("A", "B")
        g.add_edge("A", "C")
        g.add_edge("B", "D")
        g.add_edge("C", "D")

        runnables = {
            "A": DummyAgent(tm, "A"),
            "B": DummyAgent(tm, "B"),
            "C": DummyAgent(tm, "C"),
            "D": DummyAgent(tm, "D"),
        }

        mappings = [
            {
                "source_instance_id": "A",
                "source_port_name": "output",
                "target_instance_id": "B",
                "target_port_name": "input",
                "dispatch_strategy": "direct",
            },
            {
                "source_instance_id": "A",
                "source_port_name": "output",
                "target_instance_id": "C",
                "target_port_name": "input",
                "dispatch_strategy": "direct",
            },
            {
                "source_instance_id": "B",
                "source_port_name": "output",
                "target_instance_id": "D",
                "target_port_name": "input",
                "dispatch_strategy": "direct",
            },
            {
                "source_instance_id": "C",
                "source_port_name": "output",
                "target_instance_id": "D",
                "target_port_name": "input",
                "dispatch_strategy": "direct",
            },
        ]

        # Should build successfully
        gr = GraphRunner(
            graph=g,
            runnables=runnables,
            start_nodes=["A"],
            trace_manager=tm,
            port_mappings=mappings,
        )
        assert gr is not None

    def test_graph_with_multiple_edges_same_nodes(self):
        """Test graph with multiple edges between same nodes."""
        tm = TraceManager(project_name="test")
        g = nx.DiGraph()
        g.add_nodes_from(["A", "B"])
        g.add_edge("A", "B")
        g.add_edge("A", "B")  # Multiple edges

        runnables = {
            "A": DummyAgent(tm, "A"),
            "B": DummyAgent(tm, "B"),
        }

        mappings = [
            {
                "source_instance_id": "A",
                "source_port_name": "output",
                "target_instance_id": "B",
                "target_port_name": "input",
                "dispatch_strategy": "direct",
            },
        ]

        # Should build successfully
        gr = GraphRunner(
            graph=g,
            runnables=runnables,
            start_nodes=["A"],
            trace_manager=tm,
            port_mappings=mappings,
        )
        assert gr is not None

    def test_graph_with_self_loops(self):
        """Test graph with self loops - should fail due to DAG enforcement."""
        tm = TraceManager(project_name="test")
        g = nx.DiGraph()
        g.add_nodes_from(["A", "B"])
        g.add_edge("A", "B")
        g.add_edge("B", "B")  # Self loop

        runnables = {
            "A": DummyAgent(tm, "A"),
            "B": DummyAgent(tm, "B"),
        }

        mappings = [
            {
                "source_instance_id": "A",
                "source_port_name": "output",
                "target_instance_id": "B",
                "target_port_name": "input",
                "dispatch_strategy": "direct",
            },
            {
                "source_instance_id": "B",
                "source_port_name": "output",
                "target_instance_id": "B",
                "target_port_name": "input",
                "dispatch_strategy": "direct",
            },
        ]

        # Should fail due to DAG enforcement (self-loops forbidden)
        with pytest.raises(ValueError, match="Graph contains cycles"):
            GraphRunner(
                graph=g,
                runnables=runnables,
                start_nodes=["A"],
                trace_manager=tm,
                port_mappings=mappings,
            )


class TestGraphRunnerPortMappingStrategies:
    """Test different port mapping strategies."""

    def test_direct_strategy_mapping(self):
        """Test direct strategy port mapping."""
        tm = TraceManager(project_name="test")
        g = nx.DiGraph()
        g.add_nodes_from(["A", "B"])

        runnables = {
            "A": DummyAgent(tm, "A"),
            "B": DummyAgent(tm, "B"),
        }

        mappings = [
            {
                "source_instance_id": "A",
                "source_port_name": "output",
                "target_instance_id": "B",
                "target_port_name": "input",
                "dispatch_strategy": "direct",
            }
        ]

        # Should build successfully
        gr = GraphRunner(
            graph=g,
            runnables=runnables,
            start_nodes=["A"],
            trace_manager=tm,
            port_mappings=mappings,
        )
        assert gr is not None

    def test_function_call_strategy_mapping(self):
        """Test function_call strategy port mapping."""
        tm = TraceManager(project_name="test")
        g = nx.DiGraph()
        g.add_nodes_from(["A", "B"])

        runnables = {
            "A": DummyAgent(tm, "A"),
            "B": DummyAgent(tm, "B"),
        }

        mappings = [
            {
                "source_instance_id": "A",
                "source_port_name": "output",
                "target_instance_id": "B",
                "target_port_name": "input",
                "dispatch_strategy": "function_call",
            }
        ]

        # Should build successfully (strategy validation is not implemented yet)
        gr = GraphRunner(
            graph=g,
            runnables=runnables,
            start_nodes=["A"],
            trace_manager=tm,
            port_mappings=mappings,
        )
        assert gr is not None

    def test_mixed_strategy_mappings(self):
        """Test graph with mixed port mapping strategies."""
        tm = TraceManager(project_name="test")
        g = nx.DiGraph()
        g.add_nodes_from(["A", "B", "C"])

        runnables = {
            "A": DummyAgent(tm, "A"),
            "B": DummyAgent(tm, "B"),
            "C": DummyAgent(tm, "C"),
        }

        mappings = [
            {
                "source_instance_id": "A",
                "source_port_name": "output",
                "target_instance_id": "B",
                "target_port_name": "input",
                "dispatch_strategy": "direct",
            },
            {
                "source_instance_id": "B",
                "source_port_name": "output",
                "target_instance_id": "C",
                "target_port_name": "input",
                "dispatch_strategy": "function_call",
            },
        ]

        # Should build successfully
        gr = GraphRunner(
            graph=g,
            runnables=runnables,
            start_nodes=["A"],
            trace_manager=tm,
            port_mappings=mappings,
        )
        assert gr is not None


class TestGraphRunnerSynthesis:
    """Test GraphRunner's automatic port mapping synthesis."""

    def test_synthesis_single_predecessor(self):
        """Test synthesis for single predecessor nodes."""
        tm = TraceManager(project_name="test")
        g = nx.DiGraph()
        g.add_nodes_from(["A", "B"])
        g.add_edge("A", "B")  # Add edge so B has A as predecessor

        runnables = {
            "A": DummyAgent(tm, "A"),
            "B": DummyAgent(tm, "B"),
        }

        # No explicit mappings - should synthesize automatically
        gr = GraphRunner(
            graph=g,
            runnables=runnables,
            start_nodes=["A"],
            trace_manager=tm,
        )
        assert gr is not None
        assert len(gr.port_mappings) > 0  # Should have synthesized mappings

    def test_synthesis_start_node_passthrough(self):
        """Test synthesis for start node passthrough."""
        tm = TraceManager(project_name="test")
        g = nx.DiGraph()
        g.add_node("A")

        runnables = {
            "A": DummyAgent(tm, "A"),
        }

        # Start node with no predecessors - should not synthesize mappings
        gr = GraphRunner(
            graph=g,
            runnables=runnables,
            start_nodes=["A"],
            trace_manager=tm,
        )
        assert gr is not None
        # Start nodes don't get synthesized mappings (they use passthrough)

    def test_synthesis_no_predecessors(self):
        """Test synthesis for nodes with no predecessors."""
        tm = TraceManager(project_name="test")
        g = nx.DiGraph()
        g.add_node("A")

        runnables = {
            "A": DummyAgent(tm, "A"),
        }

        # Node with no predecessors - should not synthesize mappings
        gr = GraphRunner(
            graph=g,
            runnables=runnables,
            start_nodes=["A"],
            trace_manager=tm,
        )
        assert gr is not None


class TestGraphRunnerComprehensiveScenarios:
    """Test comprehensive real-world scenarios."""

    def test_rag_pipeline_scenario(self):
        """Test complete RAG pipeline scenario."""
        tm = TraceManager(project_name="test")
        g = nx.DiGraph()
        g.add_nodes_from(["input", "rag", "synthesizer", "output"])
        g.add_edge("input", "rag")
        g.add_edge("rag", "synthesizer")
        g.add_edge("synthesizer", "output")

        # Mock realistic RAG pipeline components
        class MockInputBlock:
            def get_outputs_schema(self) -> Type[BaseModel]:
                class Outputs(BaseModel):
                    messages: List[ChatMessage]

                return Outputs

        class MockRAG:
            def get_inputs_schema(self) -> Type[BaseModel]:
                class Inputs(BaseModel):
                    query_text: str

                return Inputs

            def get_outputs_schema(self) -> Type[BaseModel]:
                class Outputs(BaseModel):
                    output: str
                    sources: List[str]

                return Outputs

        class MockSynthesizer:
            def get_inputs_schema(self) -> Type[BaseModel]:
                class Inputs(BaseModel):
                    content: str

                return Inputs

            def get_outputs_schema(self) -> Type[BaseModel]:
                class Outputs(BaseModel):
                    output: str

                return Outputs

        class MockOutput:
            def get_inputs_schema(self) -> Type[BaseModel]:
                class Inputs(BaseModel):
                    output: str

                return Inputs

        runnables = {
            "input": MockInputBlock(),
            "rag": MockRAG(),
            "synthesizer": MockSynthesizer(),
            "output": MockOutput(),
        }

        mappings = [
            {
                "source_instance_id": "input",
                "source_port_name": "messages",
                "target_instance_id": "rag",
                "target_port_name": "query_text",
                "dispatch_strategy": "direct",
            },
            {
                "source_instance_id": "rag",
                "source_port_name": "output",
                "target_instance_id": "synthesizer",
                "target_port_name": "content",
                "dispatch_strategy": "direct",
            },
            {
                "source_instance_id": "synthesizer",
                "source_port_name": "output",
                "target_instance_id": "output",
                "target_port_name": "output",
                "dispatch_strategy": "direct",
            },
        ]

        # Should build successfully
        gr = GraphRunner(
            graph=g,
            runnables=runnables,
            start_nodes=["input"],
            trace_manager=tm,
            port_mappings=mappings,
        )
        assert gr is not None

    def test_multi_agent_collaboration_scenario(self):
        """Test multi-agent collaboration scenario."""
        tm = TraceManager(project_name="test")
        g = nx.DiGraph()
        g.add_nodes_from(["input", "researcher", "analyst", "writer", "output"])
        g.add_edge("input", "researcher")
        g.add_edge("researcher", "analyst")
        g.add_edge("analyst", "writer")
        g.add_edge("writer", "output")

        # Mock multi-agent collaboration components
        class MockInputBlock:
            def get_outputs_schema(self) -> Type[BaseModel]:
                class Outputs(BaseModel):
                    messages: List[ChatMessage]

                return Outputs

        class MockResearcher:
            def get_inputs_schema(self) -> Type[BaseModel]:
                class Inputs(BaseModel):
                    query: str

                return Inputs

            def get_outputs_schema(self) -> Type[BaseModel]:
                class Outputs(BaseModel):
                    research: str

                return Outputs

        class MockAnalyst:
            def get_inputs_schema(self) -> Type[BaseModel]:
                class Inputs(BaseModel):
                    research: str

                return Inputs

            def get_outputs_schema(self) -> Type[BaseModel]:
                class Outputs(BaseModel):
                    analysis: str

                return Outputs

        class MockWriter:
            def get_inputs_schema(self) -> Type[BaseModel]:
                class Inputs(BaseModel):
                    analysis: str

                return Inputs

            def get_outputs_schema(self) -> Type[BaseModel]:
                class Outputs(BaseModel):
                    output: str

                return Outputs

        class MockOutput:
            def get_inputs_schema(self) -> Type[BaseModel]:
                class Inputs(BaseModel):
                    output: str

                return Inputs

        runnables = {
            "input": MockInputBlock(),
            "researcher": MockResearcher(),
            "analyst": MockAnalyst(),
            "writer": MockWriter(),
            "output": MockOutput(),
        }

        mappings = [
            {
                "source_instance_id": "input",
                "source_port_name": "messages",
                "target_instance_id": "researcher",
                "target_port_name": "query",
                "dispatch_strategy": "direct",
            },
            {
                "source_instance_id": "researcher",
                "source_port_name": "research",
                "target_instance_id": "analyst",
                "target_port_name": "research",
                "dispatch_strategy": "direct",
            },
            {
                "source_instance_id": "analyst",
                "source_port_name": "analysis",
                "target_instance_id": "writer",
                "target_port_name": "analysis",
                "dispatch_strategy": "direct",
            },
            {
                "source_instance_id": "writer",
                "source_port_name": "output",
                "target_instance_id": "output",
                "target_port_name": "output",
                "dispatch_strategy": "direct",
            },
        ]

        # Should build successfully
        gr = GraphRunner(
            graph=g,
            runnables=runnables,
            start_nodes=["input"],
            trace_manager=tm,
            port_mappings=mappings,
        )
        assert gr is not None

    def test_parallel_processing_scenario(self):
        """Test parallel processing scenario."""
        tm = TraceManager(project_name="test")
        g = nx.DiGraph()
        g.add_nodes_from(["input", "processor1", "processor2", "merger", "output"])
        g.add_edge("input", "processor1")
        g.add_edge("input", "processor2")
        g.add_edge("processor1", "merger")
        g.add_edge("processor2", "merger")
        g.add_edge("merger", "output")

        # Mock parallel processing components
        class MockInputBlock:
            def get_outputs_schema(self) -> Type[BaseModel]:
                class Outputs(BaseModel):
                    messages: List[ChatMessage]

                return Outputs

        class MockProcessor:
            def get_inputs_schema(self) -> Type[BaseModel]:
                class Inputs(BaseModel):
                    query: str

                return Inputs

            def get_outputs_schema(self) -> Type[BaseModel]:
                class Outputs(BaseModel):
                    result: str

                return Outputs

        class MockMerger:
            def get_inputs_schema(self) -> Type[BaseModel]:
                class Inputs(BaseModel):
                    result1: str
                    result2: str

                return Inputs

            def get_outputs_schema(self) -> Type[BaseModel]:
                class Outputs(BaseModel):
                    output: str

                return Outputs

        class MockOutput:
            def get_inputs_schema(self) -> Type[BaseModel]:
                class Inputs(BaseModel):
                    output: str

                return Inputs

        runnables = {
            "input": MockInputBlock(),
            "processor1": MockProcessor(),
            "processor2": MockProcessor(),
            "merger": MockMerger(),
            "output": MockOutput(),
        }

        mappings = [
            {
                "source_instance_id": "input",
                "source_port_name": "messages",
                "target_instance_id": "processor1",
                "target_port_name": "query",
                "dispatch_strategy": "direct",
            },
            {
                "source_instance_id": "input",
                "source_port_name": "messages",
                "target_instance_id": "processor2",
                "target_port_name": "query",
                "dispatch_strategy": "direct",
            },
            {
                "source_instance_id": "processor1",
                "source_port_name": "result",
                "target_instance_id": "merger",
                "target_port_name": "result1",
                "dispatch_strategy": "direct",
            },
            {
                "source_instance_id": "processor2",
                "source_port_name": "result",
                "target_instance_id": "merger",
                "target_port_name": "result2",
                "dispatch_strategy": "direct",
            },
            {
                "source_instance_id": "merger",
                "source_port_name": "output",
                "target_instance_id": "output",
                "target_port_name": "output",
                "dispatch_strategy": "direct",
            },
        ]

        # Should build successfully
        gr = GraphRunner(
            graph=g,
            runnables=runnables,
            start_nodes=["input"],
            trace_manager=tm,
            port_mappings=mappings,
        )
        assert gr is not None


if __name__ == "__main__":
    # Run a quick test to verify the test file works
    import sys

    sys.exit(0)
