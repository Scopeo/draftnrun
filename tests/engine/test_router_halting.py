"""Regression tests for halted router branches polluting the final output."""

import asyncio
from typing import Any, Optional

import networkx as nx
from pydantic import BaseModel, PrivateAttr

from engine.components.component import Component
from engine.components.types import ComponentAttributes, ExecutionDirective, ExecutionStrategy, ToolDescription
from engine.field_expressions.serializer import from_json as expr_from_json
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

        assert gr.tasks["router2"].state == TaskState.HALTED
        assert gr.tasks["fixed_b"].state == TaskState.HALTED
        assert gr.tasks["fixed_c"].state == TaskState.HALTED
        assert gr.tasks["fixed_a"].state == TaskState.COMPLETED


class ConfigurableRouter(Component):
    """Selects a configurable edge index."""

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

    def __init__(self, trace_manager: TraceManager, selected_index: int, name: str = "router"):
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
        self._selected_index = selected_index

    async def _run_without_io_trace(self, inputs: Inputs, ctx: dict) -> Outputs:  # type: ignore
        result = self.Outputs(output=inputs.input)
        result._directive = ExecutionDirective(
            strategy=ExecutionStrategy.SELECTIVE_EDGE_INDICES,
            selected_edge_indices=[self._selected_index],
        )
        return result


def _build_graph_with_data_portmapping_across_routers(tm: TraceManager) -> GraphRunner:
    """
    Reproduces the scenario where a field expression from router1 to a grandchild node
    (leaf_c) creates an augmented dependency edge. Without the fix this augmented
    edge (order=None) causes _execute_selective_edges_indices to halt leaf_c even
    though it is on the selected path through router2.

    Graph topology (execution edges):

        router1 ── (order=0) ──▶ leaf_a
                └─ (order=1) ──▶ router2 ── (order=0) ──▶ leaf_b
                                          └─ (order=1) ──▶ leaf_c

    Data expression (adds dependency edge, no execution edge):
        router1.output ──▶ leaf_c.input

    Scenario: router1 selects 1 (→ router2), router2 selects 1 (→ leaf_c).
    Expected: leaf_c runs and returns "Response C".
    Bug: without the fix, _augment_graph_with_dependencies adds an edge
         router1 → leaf_c (no order). _execute_selective_edges_indices then
         halts leaf_c because None ∉ [1], so output is empty.
    """
    g = nx.DiGraph()
    g.add_nodes_from(["router1", "router2", "leaf_a", "leaf_b", "leaf_c"])
    g.add_edge("router1", "leaf_a", order=0)
    g.add_edge("router1", "router2", order=1)
    g.add_edge("router2", "leaf_b", order=0)
    g.add_edge("router2", "leaf_c", order=1)

    runnables = {
        "router1": ConfigurableRouter(tm, selected_index=1, name="router1"),
        "router2": ConfigurableRouter(tm, selected_index=1, name="router2"),
        "leaf_a": FixedResponse(tm, message="Response A", name="leaf_a"),
        "leaf_b": FixedResponse(tm, message="Response B", name="leaf_b"),
        "leaf_c": FixedResponse(tm, message="Response C", name="leaf_c"),
    }

    expressions = [
        {
            "target_instance_id": "leaf_c",
            "field_name": "input",
            "expression_ast": expr_from_json({"type": "ref", "instance": "router1", "port": "output"}),
        }
    ]

    return GraphRunner(
        graph=g,
        runnables=runnables,
        start_nodes=["router1"],
        trace_manager=tm,
        expressions=expressions,
    )


class TestAugmentedEdgeWithRouter:
    def test_leaf_reachable_via_nested_router_with_data_portmapping_executes(self):
        """
        Regression: leaf_c must execute when it is on the selected path through router2,
        even though a field expression ref from router1 creates an augmented dependency
        edge router1 → leaf_c (which router1's selective routing would otherwise halt).
        """
        tm = TraceManager(project_name="test")
        set_tracing_span(project_id="test_proj", organization_id="org", organization_llm_providers=["mock"])

        result = asyncio.run(_build_graph_with_data_portmapping_across_routers(tm).run({"input": "hello"}))

        assert len(result.messages) == 1
        assert result.messages[0].content == "Response C"

    def test_leaf_reachable_via_nested_router_states(self):
        """Halted nodes are HALTED, executed leaf is COMPLETED."""
        tm = TraceManager(project_name="test")
        set_tracing_span(project_id="test_proj", organization_id="org", organization_llm_providers=["mock"])

        gr = _build_graph_with_data_portmapping_across_routers(tm)
        asyncio.run(gr.run({"input": "hello"}))

        assert gr.tasks["leaf_c"].state == TaskState.COMPLETED
        assert gr.tasks["leaf_a"].state == TaskState.HALTED
        assert gr.tasks["leaf_b"].state == TaskState.HALTED
