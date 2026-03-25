"""Regression tests for halted router branches polluting the final output."""

import asyncio
from typing import Any, Optional

import networkx as nx
from pydantic import BaseModel, PrivateAttr

from engine.components.component import Component
from engine.components.types import ComponentAttributes, ExecutionDirective, ExecutionStrategy, ToolDescription
from engine.graph_runner.graph_runner import GraphRunner
from engine.graph_runner.types import TaskState
from engine.trace.span_context import set_tracing_span
from engine.trace.trace_manager import TraceManager


class SelectiveRouter(Component):
    """Always selects edge index 0."""

    migrated = True

    class Inputs(BaseModel):
        input: Any = None

    class Outputs(BaseModel):
        output: Any = None
        _directive: Optional[ExecutionDirective] = PrivateAttr(default=None)

    @classmethod
    def get_inputs_schema(cls):
        return cls.Inputs

    @classmethod
    def get_outputs_schema(cls):
        return cls.Outputs

    def __init__(self, trace_manager: TraceManager, name: str = "router"):
        super().__init__(
            trace_manager=trace_manager,
            tool_description=ToolDescription(
                name=name,
                description="",
                tool_properties={},
                required_tool_properties=[],
            ),
            component_attributes=ComponentAttributes(component_instance_name=name),
        )

    async def _run_without_io_trace(self, inputs: Inputs, ctx: dict) -> Outputs:  # type: ignore
        result = self.Outputs(output=inputs.input)
        result._directive = ExecutionDirective(
            strategy=ExecutionStrategy.SELECTIVE_EDGE_INDICES,
            selected_edge_indices=[0],
        )
        return result


class FixedResponse(Component):
    """Outputs a fixed string."""

    migrated = True

    class Inputs(BaseModel):
        input: Any = None

    class Outputs(BaseModel):
        output: str

    @classmethod
    def get_inputs_schema(cls):
        return cls.Inputs

    @classmethod
    def get_outputs_schema(cls):
        return cls.Outputs

    def __init__(self, trace_manager: TraceManager, message: str, name: str = "response"):
        super().__init__(
            trace_manager=trace_manager,
            tool_description=ToolDescription(
                name=name,
                description="",
                tool_properties={},
                required_tool_properties=[],
            ),
            component_attributes=ComponentAttributes(component_instance_name=name),
        )
        self._message = message

    async def _run_without_io_trace(self, inputs: Inputs, ctx: dict) -> Outputs:  # type: ignore
        return self.Outputs(output=self._message)


def _build_two_layer_router_graph(tm: TraceManager) -> GraphRunner:
    """
    router1 ── (order=0) ──▶ fixed_a
            └─ (order=1) ──▶ router2 ── (order=0) ──▶ fixed_b
                                      └─ (order=1) ──▶ fixed_c

    router1 always takes edge 0, so router2's branch is never executed.
    """
    g = nx.DiGraph()
    g.add_nodes_from(["router1", "router2", "fixed_a", "fixed_b", "fixed_c"])
    g.add_edge("router1", "fixed_a", order=0)
    g.add_edge("router1", "router2", order=1)
    g.add_edge("router2", "fixed_b", order=0)
    g.add_edge("router2", "fixed_c", order=1)

    runnables = {
        "router1": SelectiveRouter(tm, name="router1"),
        "router2": SelectiveRouter(tm, name="router2"),
        "fixed_a": FixedResponse(tm, message="Response A", name="fixed_a"),
        "fixed_b": FixedResponse(tm, message="Response B", name="fixed_b"),
        "fixed_c": FixedResponse(tm, message="Response C", name="fixed_c"),
    }

    return GraphRunner(graph=g, runnables=runnables, start_nodes=["router1"], trace_manager=tm)


class TestRouterHalting:
    def test_only_taken_branch_output_is_returned(self):
        tm = TraceManager(project_name="test")
        set_tracing_span(project_id="test_proj", organization_id="org", organization_llm_providers=["mock"])

        result = asyncio.run(_build_two_layer_router_graph(tm).run({"input": "hello"}))

        assert len(result.messages) == 1
        assert result.messages[0].content == "Response A"

    def test_halted_nodes_have_halted_state(self):
        tm = TraceManager(project_name="test")
        set_tracing_span(project_id="test_proj", organization_id="org", organization_llm_providers=["mock"])

        gr = _build_two_layer_router_graph(tm)
        asyncio.run(gr.run({"input": "hello"}))

        assert gr.tasks["fixed_b"].state == TaskState.HALTED
        assert gr.tasks["fixed_c"].state == TaskState.HALTED
        assert gr.tasks["fixed_a"].state == TaskState.COMPLETED
