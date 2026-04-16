"""Regression test: trace_id must be set on TracingSpanParams even when execution fails."""

import asyncio
import uuid
from unittest.mock import patch

import networkx as nx
import pytest
from pydantic import BaseModel

from engine.components.component import Component
from engine.components.types import ComponentAttributes, ToolDescription
from engine.graph_runner.graph_runner import GraphRunner
from engine.trace.span_context import get_tracing_span, set_tracing_span
from engine.trace.trace_manager import TraceManager


class _FailingInputs(BaseModel):
    input: str


class _FailingOutputs(BaseModel):
    output: str


class FailingComponent(Component):
    migrated = True

    @classmethod
    def get_inputs_schema(cls):
        return _FailingInputs

    @classmethod
    def get_outputs_schema(cls):
        return _FailingOutputs

    def __init__(self, trace_manager: TraceManager, name: str = "fail"):
        super().__init__(
            trace_manager=trace_manager,
            tool_description=ToolDescription(
                name=f"Failing_{name}",
                description="Always fails",
                tool_properties={},
                required_tool_properties=[],
            ),
            component_attributes=ComponentAttributes(
                component_instance_id=uuid.uuid4(),
                component_instance_name=f"failing_{name}",
            ),
        )

    async def _run_without_io_trace(self, inputs, ctx=None):
        raise RuntimeError("simulated component failure")


class TestTraceIdSetOnFailure:
    def test_trace_id_is_set_when_execution_fails(self):
        """trace_id must be stored in TracingSpanParams before execution
        so that callers can link a failed run to its trace."""
        tm = TraceManager(project_name="test", use_simple_processor=True)
        set_tracing_span(
            project_id="proj",
            organization_id="org",
            organization_llm_providers=["mock"],
        )

        g = nx.DiGraph()
        g.add_node("A")
        runnables = {"A": FailingComponent(tm)}

        gr = GraphRunner(
            graph=g,
            runnables=runnables,
            start_nodes=["A"],
            trace_manager=tm,
        )

        with patch(
            "engine.graph_runner.graph_runner.set_tracing_span",
            wraps=set_tracing_span,
        ) as mock_set_tracing_span:
            with pytest.raises(RuntimeError, match="simulated component failure"):
                asyncio.run(gr.run({"input": "hello"}, is_root_execution=True))

        params = get_tracing_span()
        assert params is not None
        assert params.trace_id is not None, "trace_id should be set even when execution fails"
        assert any(call.kwargs.get("trace_id") == params.trace_id for call in mock_set_tracing_span.call_args_list)
