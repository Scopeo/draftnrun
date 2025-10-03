import asyncio
from typing import Any
from unittest.mock import MagicMock, patch

import networkx as nx
import pytest
from pydantic import BaseModel

from engine.agent.agent import Agent
from engine.agent.static_responder import StaticResponder
from engine.agent.types import AgentPayload, ChatMessage, ComponentAttributes, ToolDescription
from engine.graph_runner.graph_runner import GraphRunner
from engine.trace.trace_manager import TraceManager
from tests.mocks.dummy_agent import DummyAgent


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


def test_start_node_passthrough_with_static_responder():
    tm = TraceManager(project_name="test")
    # Single node graph: start node should receive initial input via passthrough
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


def test_synthesized_default_mapping_single_predecessor():
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


def test_explicit_direct_mapping_takes_effect():
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


def test_multiple_predecessors_without_mappings_raises():
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


def test_legacy_dummy_agent_interop():

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
