from unittest.mock import MagicMock

import networkx as nx
import pytest
from pydantic import BaseModel

from engine.components.component import Component
from engine.components.if_else import (
    Condition,
    IfElse,
    IfElseInputs,
    IfElseOutputs,
)
from engine.components.types import ComponentAttributes, ExecutionStrategy, ToolDescription
from engine.graph_runner.graph_runner import GraphRunner
from engine.graph_runner.types import TaskState
from engine.trace.span_context import set_tracing_span
from engine.trace.trace_manager import TraceManager


class FixedResponse(Component):
    migrated = True

    class Inputs(BaseModel):
        input: str | None = None

    class Outputs(BaseModel):
        output: str

    @classmethod
    def get_inputs_schema(cls):
        return cls.Inputs

    @classmethod
    def get_outputs_schema(cls):
        return cls.Outputs

    def __init__(self, trace_manager: TraceManager, message: str, name: str):
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


@pytest.fixture
def mock_trace_manager():
    return MagicMock(spec=TraceManager)


@pytest.fixture
def if_else_component(mock_trace_manager):
    return IfElse(
        trace_manager=mock_trace_manager,
        component_attributes=ComponentAttributes(component_instance_name="test_if_else"),
    )


@pytest.mark.asyncio
async def test_if_else_equals_true(if_else_component):
    conditions = [Condition(value_a=5, operator="number_equal_to", value_b=5, next_logic=None)]
    inputs = IfElseInputs(conditions=conditions, output_value_if_true="test data")
    result = await if_else_component._run_without_io_trace(inputs, {})

    assert isinstance(result, IfElseOutputs)
    assert result.result is True
    assert result.output == "test data"
    assert result.should_halt is False
    assert result._directive.strategy == ExecutionStrategy.CONTINUE
    assert result._directive.selected_edge_indices == []


@pytest.mark.asyncio
async def test_if_else_equals_true_with_false_path_enabled(mock_trace_manager):
    component = IfElse(
        trace_manager=mock_trace_manager,
        component_attributes=ComponentAttributes(component_instance_name="test_if_else"),
        enable_false_path=True,
    )
    conditions = [Condition(value_a=5, operator="number_equal_to", value_b=5, next_logic=None)]
    inputs = IfElseInputs(conditions=conditions, output_value_if_true="test data")
    result = await component._run_without_io_trace(inputs, {})

    assert result.result is True
    assert result.output == "test data"
    assert result.should_halt is False
    assert result._directive.strategy == ExecutionStrategy.SELECTIVE_EDGE_INDICES
    assert result._directive.selected_edge_indices == [0]


@pytest.mark.asyncio
async def test_if_else_equals_false(if_else_component):
    conditions = [Condition(value_a=5, operator="number_equal_to", value_b=10, next_logic=None)]
    inputs = IfElseInputs(conditions=conditions, output_value_if_true="test data")
    result = await if_else_component._run_without_io_trace(inputs, {})

    assert isinstance(result, IfElseOutputs)
    assert result.result is False
    assert result.output is None
    assert result.should_halt is True
    assert result._directive.strategy == ExecutionStrategy.SELECTIVE_EDGE_INDICES
    assert result._directive.selected_edge_indices == []


@pytest.mark.asyncio
async def test_if_else_equals_false_with_false_path_enabled(mock_trace_manager):
    component = IfElse(
        trace_manager=mock_trace_manager,
        component_attributes=ComponentAttributes(component_instance_name="test_if_else"),
        enable_false_path=True,
    )
    conditions = [Condition(value_a=5, operator="number_equal_to", value_b=10, next_logic=None)]
    inputs = IfElseInputs(conditions=conditions, output_value_if_true="test data")
    result = await component._run_without_io_trace(inputs, {})

    assert result.result is False
    assert result.output is None
    assert result.should_halt is True
    assert result._directive.strategy == ExecutionStrategy.SELECTIVE_EDGE_INDICES
    assert result._directive.selected_edge_indices == [1]


@pytest.mark.asyncio
async def test_if_else_not_equals_true(mock_trace_manager):
    component = IfElse(
        trace_manager=mock_trace_manager,
        component_attributes=ComponentAttributes(component_instance_name="test_if_else"),
    )
    conditions = [Condition(value_a=5, operator="text_does_not_equal", value_b=10, next_logic=None)]
    inputs = IfElseInputs(conditions=conditions, output_value_if_true="data")
    result = await component._run_without_io_trace(inputs, {})

    assert result.result is True
    assert result.output == "data"
    assert result.should_halt is False


@pytest.mark.asyncio
async def test_if_else_not_equals_false(mock_trace_manager):
    component = IfElse(
        trace_manager=mock_trace_manager,
        component_attributes=ComponentAttributes(component_instance_name="test_if_else"),
    )
    conditions = [Condition(value_a=5, operator="text_does_not_equal", value_b=5, next_logic=None)]
    inputs = IfElseInputs(conditions=conditions)
    result = await component._run_without_io_trace(inputs, {})

    assert result.result is False
    assert result.output is None
    assert result.should_halt is True


@pytest.mark.asyncio
async def test_if_else_greater_than_true(if_else_component):
    conditions = [Condition(value_a=10, operator="number_greater_than", value_b=5, next_logic=None)]
    inputs = IfElseInputs(conditions=conditions, output_value_if_true="greater")
    result = await if_else_component._run_without_io_trace(inputs, {})

    assert result.result is True
    assert result.output == "greater"
    assert result.should_halt is False


@pytest.mark.asyncio
async def test_if_else_greater_than_false(if_else_component):
    conditions = [Condition(value_a=5, operator="number_greater_than", value_b=10, next_logic=None)]
    inputs = IfElseInputs(conditions=conditions)
    result = await if_else_component._run_without_io_trace(inputs, {})

    assert result.result is False
    assert result.should_halt is True


@pytest.mark.asyncio
async def test_if_else_less_than_true(if_else_component):
    conditions = [Condition(value_a=5, operator="number_less_than", value_b=10, next_logic=None)]
    inputs = IfElseInputs(conditions=conditions, output_value_if_true="less")
    result = await if_else_component._run_without_io_trace(inputs, {})

    assert result.result is True
    assert result.output == "less"
    assert result.should_halt is False


@pytest.mark.asyncio
async def test_if_else_less_than_false(if_else_component):
    conditions = [Condition(value_a=10, operator="number_less_than", value_b=5, next_logic=None)]
    inputs = IfElseInputs(conditions=conditions)
    result = await if_else_component._run_without_io_trace(inputs, {})

    assert result.result is False
    assert result.should_halt is True


@pytest.mark.asyncio
async def test_if_else_greater_or_equal_true_equal(if_else_component):
    conditions = [Condition(value_a=10, operator="number_greater_or_equal", value_b=10, next_logic=None)]
    inputs = IfElseInputs(conditions=conditions, output_value_if_true="equal")
    result = await if_else_component._run_without_io_trace(inputs, {})

    assert result.result is True
    assert result.output == "equal"
    assert result.should_halt is False


@pytest.mark.asyncio
async def test_if_else_greater_or_equal_true_greater(if_else_component):
    conditions = [Condition(value_a=15, operator="number_greater_or_equal", value_b=10, next_logic=None)]
    inputs = IfElseInputs(conditions=conditions, output_value_if_true="greater")
    result = await if_else_component._run_without_io_trace(inputs, {})

    assert result.result is True
    assert result.output == "greater"
    assert result.should_halt is False


@pytest.mark.asyncio
async def test_if_else_greater_or_equal_false(if_else_component):
    conditions = [Condition(value_a=5, operator="number_greater_or_equal", value_b=10, next_logic=None)]
    inputs = IfElseInputs(conditions=conditions)
    result = await if_else_component._run_without_io_trace(inputs, {})

    assert result.result is False
    assert result.should_halt is True


@pytest.mark.asyncio
async def test_if_else_less_or_equal_true_equal(if_else_component):
    conditions = [Condition(value_a=10, operator="number_less_or_equal", value_b=10, next_logic=None)]
    inputs = IfElseInputs(conditions=conditions, output_value_if_true="equal")
    result = await if_else_component._run_without_io_trace(inputs, {})

    assert result.result is True
    assert result.output == "equal"
    assert result.should_halt is False


@pytest.mark.asyncio
async def test_if_else_less_or_equal_true_less(if_else_component):
    conditions = [Condition(value_a=5, operator="number_less_or_equal", value_b=10, next_logic=None)]
    inputs = IfElseInputs(conditions=conditions, output_value_if_true="less")
    result = await if_else_component._run_without_io_trace(inputs, {})

    assert result.result is True
    assert result.output == "less"
    assert result.should_halt is False


@pytest.mark.asyncio
async def test_if_else_less_or_equal_false(if_else_component):
    conditions = [Condition(value_a=15, operator="number_less_or_equal", value_b=10, next_logic=None)]
    inputs = IfElseInputs(conditions=conditions)
    result = await if_else_component._run_without_io_trace(inputs, {})

    assert result.result is False
    assert result.should_halt is True


@pytest.mark.asyncio
async def test_if_else_string_comparison(if_else_component):
    conditions = [Condition(value_a="hello", operator="text_equals", value_b="hello", next_logic=None)]
    inputs = IfElseInputs(conditions=conditions, output_value_if_true="match")
    result = await if_else_component._run_without_io_trace(inputs, {})

    assert result.result is True
    assert result.output == "match"
    assert result.should_halt is False


@pytest.mark.asyncio
async def test_if_else_string_inequality(if_else_component):
    conditions = [Condition(value_a="hello", operator="text_equals", value_b="world", next_logic=None)]
    inputs = IfElseInputs(conditions=conditions)
    result = await if_else_component._run_without_io_trace(inputs, {})

    assert result.result is False
    assert result.should_halt is True


@pytest.mark.asyncio
async def test_if_else_numeric_string_coercion(if_else_component):
    """Test that numeric strings are coerced to numbers for comparison"""
    conditions = [Condition(value_a="5", operator="number_equal_to", value_b=5, next_logic=None)]
    inputs = IfElseInputs(conditions=conditions, output_value_if_true="coerced")
    result = await if_else_component._run_without_io_trace(inputs, {})

    assert result.result is True
    assert result.output == "coerced"
    assert result.should_halt is False


@pytest.mark.asyncio
async def test_if_else_float_comparison(if_else_component):
    conditions = [Condition(value_a=5.5, operator="number_greater_than", value_b=5.2, next_logic=None)]
    inputs = IfElseInputs(conditions=conditions, output_value_if_true="float")
    result = await if_else_component._run_without_io_trace(inputs, {})

    assert result.result is True
    assert result.output == "float"
    assert result.should_halt is False


@pytest.mark.asyncio
async def test_if_else_mixed_int_float_comparison(if_else_component):
    conditions = [Condition(value_a=5, operator="number_less_than", value_b=5.1, next_logic=None)]
    inputs = IfElseInputs(conditions=conditions, output_value_if_true="mixed")
    result = await if_else_component._run_without_io_trace(inputs, {})

    assert result.result is True
    assert result.output == "mixed"
    assert result.should_halt is False


@pytest.mark.asyncio
async def test_if_else_no_pass_through_data(if_else_component):
    """Test that when condition is true but no pass_through_data is provided, output is None"""
    conditions = [Condition(value_a=5, operator="number_equal_to", value_b=5, next_logic=None)]
    inputs = IfElseInputs(conditions=conditions)
    result = await if_else_component._run_without_io_trace(inputs, {})

    assert result.result is True
    assert result.output is None
    assert result.should_halt is False


@pytest.mark.asyncio
async def test_if_else_complex_pass_through_data(if_else_component):
    """Test that complex data structures can be passed through"""
    complex_data = {"key": "value", "nested": {"data": [1, 2, 3]}}
    conditions = [Condition(value_a=1, operator="number_equal_to", value_b=1, next_logic=None)]
    inputs = IfElseInputs(conditions=conditions, output_value_if_true=complex_data)
    result = await if_else_component._run_without_io_trace(inputs, {})

    assert result.result is True
    assert result.output == complex_data
    assert result.should_halt is False


# New tests for additional operators


@pytest.mark.asyncio
async def test_if_else_is_empty_true(if_else_component):
    """Test is_empty operator with empty values"""
    # Test with None
    conditions = [Condition(value_a=None, operator="is_empty", value_b=None, next_logic=None)]
    inputs = IfElseInputs(conditions=conditions, output_value_if_true="empty")
    result = await if_else_component._run_without_io_trace(inputs, {})
    assert result.result is True

    # Test with empty string
    conditions = [Condition(value_a="", operator="is_empty", value_b=None, next_logic=None)]
    inputs = IfElseInputs(conditions=conditions)
    result = await if_else_component._run_without_io_trace(inputs, {})
    assert result.result is True

    # Test with empty list
    conditions = [Condition(value_a=[], operator="is_empty", value_b=None, next_logic=None)]
    inputs = IfElseInputs(conditions=conditions)
    result = await if_else_component._run_without_io_trace(inputs, {})
    assert result.result is True


@pytest.mark.asyncio
async def test_if_else_is_empty_false(if_else_component):
    """Test is_empty operator with non-empty values"""
    conditions = [Condition(value_a="hello", operator="is_empty", value_b=None, next_logic=None)]
    inputs = IfElseInputs(conditions=conditions)
    result = await if_else_component._run_without_io_trace(inputs, {})
    assert result.result is False
    assert result.should_halt is True


@pytest.mark.asyncio
async def test_if_else_boolean_is_true(if_else_component):
    """Test boolean_is_true operator"""
    # Test with boolean True
    conditions = [Condition(value_a=True, operator="boolean_is_true", value_b=None, next_logic=None)]
    inputs = IfElseInputs(conditions=conditions, output_value_if_true="is true")
    result = await if_else_component._run_without_io_trace(inputs, {})
    assert result.result is True
    assert result.output == "is true"

    # Test with string "true"
    conditions = [Condition(value_a="true", operator="boolean_is_true", value_b=None, next_logic=None)]
    inputs = IfElseInputs(conditions=conditions)
    result = await if_else_component._run_without_io_trace(inputs, {})
    assert result.result is True

    # Test with False
    conditions = [Condition(value_a=False, operator="boolean_is_true", value_b=None, next_logic=None)]
    inputs = IfElseInputs(conditions=conditions)
    result = await if_else_component._run_without_io_trace(inputs, {})
    assert result.result is False


@pytest.mark.asyncio
async def test_if_else_text_contains(if_else_component):
    """Test text_contains operator"""
    # Test positive case
    conditions = [Condition(value_a="Hello world!", operator="text_contains", value_b="world", next_logic=None)]
    inputs = IfElseInputs(conditions=conditions, output_value_if_true="contains")
    result = await if_else_component._run_without_io_trace(inputs, {})
    assert result.result is True
    assert result.output == "contains"

    # Test negative case
    conditions = [Condition(value_a="Hello world!", operator="text_contains", value_b="goodbye", next_logic=None)]
    inputs = IfElseInputs(conditions=conditions)
    result = await if_else_component._run_without_io_trace(inputs, {})
    assert result.result is False
    assert result.should_halt is True


@pytest.mark.asyncio
async def test_if_else_text_does_not_contain(if_else_component):
    """Test text_does_not_contain operator"""
    conditions = [
        Condition(value_a="Hello world!", operator="text_does_not_contain", value_b="goodbye", next_logic=None)
    ]
    inputs = IfElseInputs(conditions=conditions, output_value_if_true="no contain")
    result = await if_else_component._run_without_io_trace(inputs, {})
    assert result.result is True
    assert result.output == "no contain"


# Advanced mode tests (multiple conditions)


@pytest.mark.asyncio
async def test_if_else_multiple_conditions_and(mock_trace_manager):
    """Test multiple conditions with AND logic"""
    component = IfElse(
        trace_manager=mock_trace_manager,
        component_attributes=ComponentAttributes(component_instance_name="test_if_else"),
    )

    conditions = [
        Condition(value_a=10, operator="number_greater_than", value_b=5, next_logic="AND"),
        Condition(value_a=10, operator="number_less_than", value_b=20, next_logic=None),
    ]

    inputs = IfElseInputs(conditions=conditions, output_value_if_true="both true")
    result = await component._run_without_io_trace(inputs, {})

    assert result.result is True
    assert result.output == "both true"
    assert result.should_halt is False


@pytest.mark.asyncio
async def test_if_else_multiple_conditions_and_false(mock_trace_manager):
    """Test multiple conditions with AND logic where one is false"""
    component = IfElse(
        trace_manager=mock_trace_manager,
        component_attributes=ComponentAttributes(component_instance_name="test_if_else"),
    )

    conditions = [
        Condition(value_a=10, operator="number_greater_than", value_b=5, next_logic="AND"),
        Condition(
            value_a=10,
            operator="number_greater_than",
            value_b=20,  # This is false
            next_logic=None,
        ),
    ]

    inputs = IfElseInputs(conditions=conditions)
    result = await component._run_without_io_trace(inputs, {})

    assert result.result is False
    assert result.output is None
    assert result.should_halt is True


@pytest.mark.asyncio
async def test_if_else_multiple_conditions_or(mock_trace_manager):
    """Test multiple conditions with OR logic"""
    component = IfElse(
        trace_manager=mock_trace_manager,
        component_attributes=ComponentAttributes(component_instance_name="test_if_else"),
    )

    conditions = [
        Condition(
            value_a=10,
            operator="number_greater_than",
            value_b=20,  # False
            next_logic="OR",
        ),
        Condition(
            value_a="test",
            operator="text_equals",
            value_b="test",  # True
            next_logic=None,
        ),
    ]

    inputs = IfElseInputs(conditions=conditions, output_value_if_true="one true")
    result = await component._run_without_io_trace(inputs, {})

    assert result.result is True
    assert result.output == "one true"
    assert result.should_halt is False


@pytest.mark.asyncio
async def test_if_else_multiple_conditions_mixed_logic(mock_trace_manager):
    """Test multiple conditions with mixed AND/OR logic"""
    component = IfElse(
        trace_manager=mock_trace_manager,
        component_attributes=ComponentAttributes(component_instance_name="test_if_else"),
    )

    # (5 > 3 AND 10 < 20) OR (text == "wrong")
    # (True AND True) OR False = True
    conditions = [
        Condition(value_a=5, operator="number_greater_than", value_b=3, next_logic="AND"),
        Condition(value_a=10, operator="number_less_than", value_b=20, next_logic="OR"),
        Condition(value_a="test", operator="text_equals", value_b="wrong", next_logic=None),
    ]

    inputs = IfElseInputs(conditions=conditions, output_value_if_true="mixed logic")
    result = await component._run_without_io_trace(inputs, {})

    assert result.result is True
    assert result.output == "mixed logic"


# Field expressions like @{{instance_id.output}} are handled automatically by the framework
# before reaching the component, so we don't need to test field expression resolution here


def _build_if_else_graph(
    trace_manager: TraceManager,
    include_else: bool = True,
    true_edge_order: int | None = 0,
) -> GraphRunner:
    graph = nx.DiGraph()
    graph.add_nodes_from(["if_else", "true_leaf"])
    graph.add_edge("if_else", "true_leaf", order=true_edge_order)

    runnables = {
        "if_else": IfElse(
            trace_manager=trace_manager,
            component_attributes=ComponentAttributes(component_instance_name="if_else"),
            enable_false_path=include_else,
        ),
        "true_leaf": FixedResponse(trace_manager, message="true branch", name="true_leaf"),
    }

    if include_else:
        graph.add_node("else_leaf")
        graph.add_edge("if_else", "else_leaf", order=1)
        runnables["else_leaf"] = FixedResponse(trace_manager, message="else branch", name="else_leaf")

    return GraphRunner(graph=graph, runnables=runnables, start_nodes=["if_else"], trace_manager=trace_manager)


@pytest.mark.asyncio
async def test_if_else_graph_executes_true_branch_only():
    set_tracing_span(project_id="test_proj", organization_id="org", organization_llm_providers=["mock"])
    graph_runner = _build_if_else_graph(TraceManager(project_name="test"))

    result = await graph_runner.run({
        "conditions": [Condition(value_a=1, operator="number_equal_to", value_b=1, next_logic=None).model_dump()],
        "output_value_if_true": "payload",
    })

    assert [message.content for message in result.messages] == ["true branch"]
    assert graph_runner.tasks["true_leaf"].state == TaskState.COMPLETED
    assert graph_runner.tasks["else_leaf"].state == TaskState.HALTED


@pytest.mark.asyncio
async def test_if_else_graph_true_without_false_path_continues_unordered_legacy_edge():
    set_tracing_span(project_id="test_proj", organization_id="org", organization_llm_providers=["mock"])
    graph_runner = _build_if_else_graph(
        TraceManager(project_name="test"),
        include_else=False,
        true_edge_order=None,
    )

    result = await graph_runner.run({
        "conditions": [Condition(value_a=1, operator="number_equal_to", value_b=1, next_logic=None).model_dump()],
        "output_value_if_true": "payload",
    })

    assert [message.content for message in result.messages] == ["true branch"]
    assert graph_runner.tasks["true_leaf"].state == TaskState.COMPLETED


@pytest.mark.asyncio
async def test_if_else_graph_executes_else_branch_when_present():
    set_tracing_span(project_id="test_proj", organization_id="org", organization_llm_providers=["mock"])
    graph_runner = _build_if_else_graph(TraceManager(project_name="test"))

    result = await graph_runner.run({
        "conditions": [Condition(value_a=1, operator="number_equal_to", value_b=2, next_logic=None).model_dump()],
        "output_value_if_true": "payload",
    })

    assert [message.content for message in result.messages] == ["else branch"]
    assert graph_runner.tasks["true_leaf"].state == TaskState.HALTED
    assert graph_runner.tasks["else_leaf"].state == TaskState.COMPLETED


@pytest.mark.asyncio
async def test_if_else_graph_false_without_else_halts_downstream():
    set_tracing_span(project_id="test_proj", organization_id="org", organization_llm_providers=["mock"])
    graph_runner = _build_if_else_graph(TraceManager(project_name="test"), include_else=False)

    result = await graph_runner.run({
        "conditions": [Condition(value_a=1, operator="number_equal_to", value_b=2, next_logic=None).model_dump()],
        "output_value_if_true": "payload",
    })

    assert [message.content for message in result.messages] == [""]
    assert graph_runner.tasks["if_else"].state == TaskState.COMPLETED
    assert graph_runner.tasks["true_leaf"].state == TaskState.HALTED
