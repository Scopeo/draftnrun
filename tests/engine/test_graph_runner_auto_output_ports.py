import asyncio
import json
from typing import Any
from unittest.mock import MagicMock, patch

import networkx as nx
from pydantic import BaseModel, Field

from engine.components.component import Component
from engine.components.types import ComponentAttributes, ToolDescription
from engine.graph_runner.graph_runner import GraphRunner


class DummySpan:
    def set_attributes(self, attributes: dict[str, Any]):
        pass

    def set_status(self, status):
        pass

    def record_exception(self, exc: Exception):
        pass

    def to_json(self) -> str:
        return json.dumps({"context": {"trace_id": "trace-id"}})


class DummySpanContextManager:
    def __enter__(self):
        return DummySpan()

    def __exit__(self, exc_type, exc, traceback):
        return False


class DummyTraceManager:
    def start_span(self, *args, **kwargs):
        return DummySpanContextManager()


class AutoPortOutputComponent(Component):
    migrated = True

    class Inputs(BaseModel):
        input: str = ""

    class Outputs(BaseModel):
        output: str
        id: str
        email: str
        ignored: str = Field(default="ignored")

    @classmethod
    def get_inputs_schema(cls):
        return cls.Inputs

    @classmethod
    def get_outputs_schema(cls):
        return cls.Outputs

    @classmethod
    def get_auto_output_port_names(cls, output_data: dict[str, Any]) -> list[str]:
        return sorted(key for key in output_data if key in {"id", "email"})

    def __init__(self, trace_manager: DummyTraceManager):
        super().__init__(
            trace_manager=trace_manager,
            tool_description=ToolDescription(
                name="auto_port_output",
                description="Outputs auto-detected ports",
                tool_properties={},
                required_tool_properties=[],
            ),
            component_attributes=ComponentAttributes(component_instance_name="auto_port_output"),
        )

    async def _run_without_io_trace(self, inputs, ctx):
        return self.Outputs(output="ok", id="contact-123", email="ada@example.com")


def test_graph_runner_emits_auto_output_port_names_on_node_completed():
    trace_manager = DummyTraceManager()
    graph = nx.DiGraph()
    graph.add_node("node-a")
    events = []

    async def event_callback(evt: dict):
        events.append(evt)

    runner = GraphRunner(
        graph=graph,
        runnables={"node-a": AutoPortOutputComponent(trace_manager)},
        start_nodes=["node-a"],
        trace_manager=trace_manager,
        event_callback=event_callback,
    )

    with (
        patch("engine.prometheus_metric.get_tracing_span") as mock_get_span,
        patch("engine.prometheus_metric.agent_calls") as mock_agent_calls,
    ):
        mock_get_span.return_value = MagicMock(project_id="test_project")
        mock_agent_calls.labels.return_value = MagicMock()
        asyncio.run(runner.run({"input": "go"}))

    assert events == [
        {"type": "node.started", "node_id": "node-a"},
        {"type": "node.completed", "node_id": "node-a", "auto_output_port_names": ["email", "id"]},
    ]
