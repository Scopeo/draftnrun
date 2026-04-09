from typing import Any
from unittest.mock import MagicMock, patch

import networkx as nx
import pytest
from pydantic import BaseModel

from engine.components.component import Component
from engine.components.types import ChatMessage, ComponentAttributes, ToolDescription
from engine.graph_runner.graph_runner import GraphRunner
from engine.graph_runner.port_management import get_component_port_type
from engine.trace.trace_manager import TraceManager

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
