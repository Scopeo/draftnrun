import asyncio
from typing import Any, Optional, Type
from unittest.mock import MagicMock, patch

import networkx as nx
import pytest
from pydantic import BaseModel

from engine.agent.agent import Agent
from engine.agent.static_responder import StaticResponder
from engine.agent.types import AgentPayload, ChatMessage, ComponentAttributes, ToolDescription
from engine.graph_runner.graph_runner import GraphRunner
from engine.graph_runner.port_management import get_component_port_type
from engine.legacy_compatibility import get_unmigrated_output_type
from engine.trace.trace_manager import TraceManager
from tests.mocks.dummy_agent import DummyAgent

# ============================================================================
# SHARED MOCK COMPONENTS - Inherit from Agent for consistency
# ============================================================================


class MockIntOutputAgent(Agent):
    """Mock agent that outputs int values."""

    migrated = True

    class Inputs(BaseModel):
        input: Any

    class Outputs(BaseModel):
        output: int

    @classmethod
    def get_inputs_schema(cls):
        return cls.Inputs

    @classmethod
    def get_outputs_schema(cls):
        return cls.Outputs

    def __init__(self, trace_manager: TraceManager, component_name: str = "int_output"):
        super().__init__(
            trace_manager=trace_manager,
            tool_description=ToolDescription(
                name=f"MockInt_{component_name}",
                description="Mock int output agent",
                tool_properties={},
                required_tool_properties=[],
            ),
            component_attributes=ComponentAttributes(component_instance_name=component_name),
        )

    async def _run_without_io_trace(self, inputs, ctx):
        return self.Outputs(output=42)


class MockListInputAgent(Agent):
    """Mock agent that expects list[ChatMessage] input."""

    migrated = True

    class Inputs(BaseModel):
        messages: list[ChatMessage]

    class Outputs(BaseModel):
        output: str

    @classmethod
    def get_inputs_schema(cls):
        return cls.Inputs

    @classmethod
    def get_outputs_schema(cls):
        return cls.Outputs

    def __init__(self, trace_manager: TraceManager, component_name: str = "list_input"):
        super().__init__(
            trace_manager=trace_manager,
            tool_description=ToolDescription(
                name=f"MockList_{component_name}",
                description="Mock list input agent",
                tool_properties={},
                required_tool_properties=[],
            ),
            component_attributes=ComponentAttributes(component_instance_name=component_name),
        )

    async def _run_without_io_trace(self, inputs, ctx):
        return self.Outputs(output="processed")


class MockUnmigratedIntOutput:
    """Mock unmigrated component that outputs int values."""

    migrated = False

    def get_outputs_schema(self) -> Type[BaseModel]:
        class Outputs(BaseModel):
            output: int

        return Outputs


class MockUnmigratedListInput:
    """Mock unmigrated component that expects list[ChatMessage] input."""

    migrated = False

    def get_inputs_schema(self) -> Type[BaseModel]:
        class Inputs(BaseModel):
            messages: list[ChatMessage]

        return Inputs


class MockUnknownComponent:
    """Mock component with no schema methods (for unknown type testing)."""

    pass


@pytest.fixture(autouse=True)
def patch_prometheus_metrics():
    """Patch prometheus metrics used by @track_calls to avoid None params in tests."""
    with (
        patch("engine.prometheus_metric.get_tracing_span") as mock_get_span,
        patch("engine.prometheus_metric.agent_calls") as mock_agent_calls,
    ):
        mock_get_span.return_value = MagicMock(project_id="test_project")
        counter = MagicMock()
        mock_agent_calls.labels.return_value = counter
        yield


class EchoAgent(Agent):
    """Deterministic migrated agent that echoes its input into an 'output' port.

    - input port: 'input'
    - output port: 'output'
    """

    migrated = True

    # Define stable schemas at module/class scope to avoid dynamic re-creation mismatches

    class Inputs(BaseModel):  # type: ignore
        input: Any

    class Outputs(BaseModel):  # type: ignore
        output: Any

    @classmethod
    def get_canonical_ports(cls):
        return {"input": "input", "output": "output"}

    @classmethod
    def get_inputs_schema(cls):
        return EchoAgent.Inputs

    @classmethod
    def get_outputs_schema(cls):
        return EchoAgent.Outputs

    def __init__(self, trace_manager: TraceManager, component_name: str = "echo"):
        super().__init__(
            trace_manager=trace_manager,
            tool_description=ToolDescription(
                name=f"Echo_{component_name}",
                description="Echoes input",
                tool_properties={},
                required_tool_properties=[],
            ),
            component_attributes=ComponentAttributes(component_instance_name=component_name),
        )

    async def _run_without_io_trace(self, inputs, ctx):
        return EchoAgent.Outputs(output=f"got:{inputs.input}")


class TestGraphRunnerPortMappings:
    """Test GraphRunner port mapping functionality."""

    def test_start_node_passthrough_with_static_responder(self):
        """Test single node graph: start node should receive initial input via passthrough."""
        tm = TraceManager(project_name="test")
        g = nx.DiGraph()
        g.add_node("A")

        runnables = {
            "A": StaticResponder(
                trace_manager=tm,
                component_attributes=ComponentAttributes(component_instance_name="A"),
                static_message="static",
            )
        }

        gr = GraphRunner(graph=g, runnables=runnables, start_nodes=["A"], trace_manager=tm)
        result = asyncio.run(gr.run({"input": "hello"}))
        assert isinstance(result, AgentPayload)
        assert result.messages[0].content == "static"

    def test_synthesized_default_mapping_single_predecessor(self):
        """Test that GraphRunner synthesizes A(static_message)->B(input) mapping."""
        tm = TraceManager(project_name="test")
        g = nx.DiGraph()
        g.add_nodes_from(["A", "B"])
        g.add_edge("A", "B")

        a = StaticResponder(
            trace_manager=tm,
            component_attributes=ComponentAttributes(component_instance_name="A"),
            static_message="foo",
        )
        b = EchoAgent(trace_manager=tm, component_name="B")
        runnables = {"A": a, "B": b}

        # No explicit mappings; GraphRunner should synthesize A(static_message)->B(input)
        gr = GraphRunner(graph=g, runnables=runnables, start_nodes=["A"], trace_manager=tm)
        result = asyncio.run(gr.run({"input": "ignored"}))
        assert isinstance(result, AgentPayload)
        # EchoAgent should receive input "foo" and return got:foo
        assert result.messages[0].content == "got:foo"

    def test_explicit_direct_mapping_takes_effect(self):
        """Test that explicit port mappings override synthesized defaults."""
        tm = TraceManager(project_name="test")
        g = nx.DiGraph()
        g.add_nodes_from(["A", "B"])
        g.add_edge("A", "B")

        a = StaticResponder(
            trace_manager=tm,
            component_attributes=ComponentAttributes(component_instance_name="A"),
            static_message="bar",
        )
        b = EchoAgent(trace_manager=tm, component_name="B")
        runnables = {"A": a, "B": b}

        mappings = [
            {
                "source_instance_id": "A",
                "source_port_name": "static_message",
                "target_instance_id": "B",
                "target_port_name": "input",
                "dispatch_strategy": "direct",
            }
        ]

        gr = GraphRunner(graph=g, runnables=runnables, start_nodes=["A"], trace_manager=tm, port_mappings=mappings)
        result = asyncio.run(gr.run({"input": "ignored"}))
        assert isinstance(result, AgentPayload)
        assert result.messages[0].content == "got:bar"

    def test_multiple_predecessors_without_mappings_raises(self):
        """Test that multiple predecessors without explicit mappings raise ValueError."""
        tm = TraceManager(project_name="test")
        g = nx.DiGraph()
        g.add_nodes_from(["A", "B", "C"])
        g.add_edge("A", "C")
        g.add_edge("B", "C")

        a = StaticResponder(
            trace_manager=tm,
            component_attributes=ComponentAttributes(component_instance_name="A"),
            static_message="a",
        )
        b = StaticResponder(
            trace_manager=tm,
            component_attributes=ComponentAttributes(component_instance_name="B"),
            static_message="b",
        )
        c = EchoAgent(trace_manager=tm, component_name="C")
        runnables = {"A": a, "B": b, "C": c}

        with pytest.raises(ValueError):
            GraphRunner(graph=g, runnables=runnables, start_nodes=["A", "B"], trace_manager=tm)

    def test_legacy_dummy_agent_interop(self):
        """Test interoperability between legacy DummyAgent and migrated EchoAgent."""
        tm = TraceManager(project_name="test")

        g = nx.DiGraph()
        g.add_nodes_from(["A", "B"])
        g.add_edge("A", "B")

        a = DummyAgent(trace_manager=tm, prefix="X")
        b = EchoAgent(trace_manager=tm, component_name="B")
        runnables = {"A": a, "B": b}

        gr = GraphRunner(graph=g, runnables=runnables, start_nodes=["A"], trace_manager=tm)
        payload = AgentPayload(messages=[ChatMessage(role="user", content="hi")])
        result = asyncio.run(gr.run(payload))
        assert isinstance(result, AgentPayload)
        # DummyAgent outputs "[X] hi" as legacy payload, GraphRunner converts to NodeData with key 'output'.
        # Synthesized mapping passes that into EchoAgent input → got:[X] hi
        assert result.messages[0].content == "got:[X] hi"


class TestTypeDiscovery:
    """Test the new two-tier type discovery system."""

    def test_migrated_component_type_discovery(self):
        """Test type discovery for migrated components."""
        tm = TraceManager(project_name="test")
        g = nx.DiGraph()
        g.add_nodes_from(["A"])

        # Create a migrated component
        migrated_agent = EchoAgent(trace_manager=tm, component_name="A")
        runnables = {"A": migrated_agent}

        GraphRunner(graph=g, runnables=runnables, start_nodes=["A"], trace_manager=tm)

        # Test input type discovery
        input_type = get_component_port_type(migrated_agent, "input", is_input=True)
        assert input_type == Any  # EchoAgent input is Any

        # Test output type discovery
        output_type = get_component_port_type(migrated_agent, "output", is_input=False)
        assert output_type == Any  # EchoAgent output is Any

    def test_unmigrated_component_type_discovery(self):
        """Test type discovery for unmigrated components."""
        tm = TraceManager(project_name="test")
        g = nx.DiGraph()
        g.add_nodes_from(["A"])

        # Create an unmigrated component (DummyAgent doesn't have migrated=True)
        unmigrated_agent = DummyAgent(trace_manager=tm, prefix="X")
        runnables = {"A": unmigrated_agent}

        GraphRunner(graph=g, runnables=runnables, start_nodes=["A"], trace_manager=tm)

        # Test output type discovery (should use pattern lookup)
        output_type = get_component_port_type(unmigrated_agent, "messages", is_input=False)
        assert output_type == list[ChatMessage]  # DummyAgent should match AgentPayload pattern

        # Test input type discovery (should use schema methods if available)
        input_type = get_component_port_type(unmigrated_agent, "input", is_input=True)
        assert input_type == Any  # DummyAgent has schema methods, so use them

    def test_pattern_lookup_for_known_components(self):
        """Test that pattern lookup works for known unmigrated components."""
        tm = TraceManager(project_name="test")
        g = nx.DiGraph()
        g.add_nodes_from(["A"])

        # Test with DummyAgent (should match AgentPayload pattern)
        dummy_agent = DummyAgent(trace_manager=tm, prefix="X")
        runnables = {"A": dummy_agent}

        GraphRunner(graph=g, runnables=runnables, start_nodes=["A"], trace_manager=tm)

        # Test AgentPayload pattern fields
        assert get_unmigrated_output_type(dummy_agent, "messages") is list[ChatMessage]
        assert get_unmigrated_output_type(dummy_agent, "artifacts") is dict
        assert get_unmigrated_output_type(dummy_agent, "error") is Optional[str]
        assert get_unmigrated_output_type(dummy_agent, "is_final") is Optional[bool]

        # Test unknown field
        assert get_unmigrated_output_type(dummy_agent, "unknown_field") is None


class TestValidationStrictness:
    """Test the new validation strictness levels."""

    def test_strict_validation_for_migrated_components(self):
        """Test that migrated components get strict validation (errors)."""
        tm = TraceManager(project_name="test")
        g = nx.DiGraph()
        g.add_nodes_from(["A", "B"])

        # Use shared mock components with incompatible types
        runnables = {
            "A": MockIntOutputAgent(tm, "A"),
            "B": MockListInputAgent(tm, "B"),
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

        # Should fail with ValueError (strict validation)
        with pytest.raises(ValueError, match="Cannot coerce"):
            GraphRunner(
                graph=g,
                runnables=runnables,
                start_nodes=["A"],
                trace_manager=tm,
                port_mappings=mappings,
            )

    def test_lenient_validation_for_unmigrated_components(self, caplog):
        """Test that unmigrated components get lenient validation (warnings)."""
        tm = TraceManager(project_name="test")
        g = nx.DiGraph()
        g.add_nodes_from(["A", "B"])

        # Use shared unmigrated mock components
        runnables = {
            "A": MockUnmigratedIntOutput(),
            "B": MockUnmigratedListInput(),
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

        # Should not fail, but should log warnings
        with caplog.at_level("WARNING"):
            GraphRunner(
                graph=g,
                runnables=runnables,
                start_nodes=["A"],
                trace_manager=tm,
                port_mappings=mappings,
            )

        # Check that warning was logged
        assert "may fail at runtime" in caplog.text
        assert "Consider migrating components" in caplog.text

    def test_info_logging_for_unknown_types(self, caplog):
        """Test that unknown types get info logging."""
        tm = TraceManager(project_name="test")
        g = nx.DiGraph()
        g.add_nodes_from(["A", "B"])

        # Use shared mock components with no schema methods
        runnables = {
            "A": MockUnknownComponent(),
            "B": MockUnknownComponent(),
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

        # Should not fail, but should log info
        with caplog.at_level("INFO"):
            GraphRunner(
                graph=g,
                runnables=runnables,
                start_nodes=["A"],
                trace_manager=tm,
                port_mappings=mappings,
            )

        # Check that info was logged
        assert "Skipping build-time validation" in caplog.text
        assert "types unknown" in caplog.text
