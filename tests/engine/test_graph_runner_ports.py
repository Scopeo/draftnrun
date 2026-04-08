import asyncio
from typing import Any, Type, get_args, get_origin
from unittest.mock import MagicMock, patch

import networkx as nx
import pytest
from pydantic import BaseModel

from engine.components.component import Component
from engine.components.static_responder import StaticResponder
from engine.components.types import AgentPayload, ChatMessage, ComponentAttributes, ToolDescription
from engine.graph_runner.graph_runner import GraphRunner
from engine.graph_runner.port_management import get_component_port_type
from engine.legacy_compatibility import get_unmigrated_output_type
from engine.trace.trace_manager import TraceManager
from tests.mocks.dummy_agent import DummyAgent

# ============================================================================
# SHARED MOCK COMPONENTS - Inherit from Agent for consistency
# ============================================================================


class MockIntOutputAgent(Component):
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


class MockListInputAgent(Component):
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


class EchoAgent(Component):
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
        messages_type = get_unmigrated_output_type(dummy_agent, "messages")
        assert get_origin(messages_type) is list
        assert get_args(messages_type) == (ChatMessage,)

        artifacts_type = get_unmigrated_output_type(dummy_agent, "artifacts")
        assert artifacts_type is dict

        error_type = get_unmigrated_output_type(dummy_agent, "error")
        assert set(get_args(error_type)) == {str, type(None)}

        is_final_type = get_unmigrated_output_type(dummy_agent, "is_final")
        assert set(get_args(is_final_type)) == {bool, type(None)}

        # Test unknown field
        assert get_unmigrated_output_type(dummy_agent, "unknown_field") is None


