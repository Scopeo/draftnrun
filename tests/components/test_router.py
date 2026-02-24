from unittest.mock import MagicMock

import pytest

from engine.components.errors import NoMatchingRouteError
from engine.components.router import RouteCondition, Router, RouterInputs
from engine.components.types import ComponentAttributes, ExecutionStrategy
from engine.trace.trace_manager import TraceManager


@pytest.fixture
def mock_trace_manager():
    return MagicMock(spec=TraceManager)


@pytest.fixture
def router_component(mock_trace_manager):
    return Router(
        trace_manager=mock_trace_manager,
        component_attributes=ComponentAttributes(component_instance_name="test_router"),
    )


@pytest.mark.asyncio
async def test_router_single_route_match(router_component):
    """Test router with single route that matches"""
    output_data = {"test": "data", "value": 123}
    inputs = RouterInputs(routes=[RouteCondition(value_a="bottle", value_b="bottle")], output_data=output_data)
    result = await router_component._run_without_io_trace(inputs, {})

    assert result._directive.strategy == ExecutionStrategy.SELECTIVE_EDGE_INDICES
    assert result._directive.selected_edge_indices == [0]
    assert result.output == output_data


@pytest.mark.asyncio
async def test_router_single_route_no_match(router_component):
    """Test router with single route that doesn't match - should raise error"""
    inputs = RouterInputs(routes=[RouteCondition(value_a="bottle", value_b="water")], output_data={"test": "data"})

    with pytest.raises(NoMatchingRouteError):
        await router_component._run_without_io_trace(inputs, {})


@pytest.mark.asyncio
async def test_router_multiple_routes_first_matches(router_component):
    """Test router with multiple routes where first matches"""
    output_data = [1, 2, 3]
    inputs = RouterInputs(
        routes=[
            RouteCondition(value_a="bottle", value_b="bottle"),  # Matches
            RouteCondition(value_a="cup", value_b="no_match"),
            RouteCondition(value_a="water", value_b="no_match"),
        ],
        output_data=output_data,
    )
    result = await router_component._run_without_io_trace(inputs, {})

    assert result._directive.selected_edge_indices == [0]
    assert result.output == output_data


@pytest.mark.asyncio
async def test_router_multiple_routes_middle_matches(router_component):
    """Test router with multiple routes where middle route matches"""
    output_data = "middle route output"
    inputs = RouterInputs(
        routes=[
            RouteCondition(value_a="bottle", value_b="no_match"),
            RouteCondition(value_a="cup", value_b="cup"),  # Matches
            RouteCondition(value_a="water", value_b="no_match"),
        ],
        output_data=output_data,
    )
    result = await router_component._run_without_io_trace(inputs, {})

    assert result._directive.selected_edge_indices == [1]
    assert result.output == output_data


@pytest.mark.asyncio
async def test_router_multiple_routes_last_matches(router_component):
    """Test router with multiple routes where last route matches"""
    output_data = 42
    inputs = RouterInputs(
        routes=[
            RouteCondition(value_a="bottle", value_b="no_match"),
            RouteCondition(value_a="cup", value_b="no_match"),
            RouteCondition(value_a="water", value_b="water"),  # Matches
        ],
        output_data=output_data,
    )
    result = await router_component._run_without_io_trace(inputs, {})

    assert result._directive.selected_edge_indices == [2]
    assert result.output == output_data


@pytest.mark.asyncio
async def test_router_no_routes_match(router_component):
    """Test router when no routes match - should raise error"""
    inputs = RouterInputs(
        routes=[
            RouteCondition(value_a="bottle", value_b="no_match"),
            RouteCondition(value_a="cup", value_b="no_match"),
            RouteCondition(value_a="water", value_b="no_match"),
        ],
        output_data={"test": "data"},
    )

    with pytest.raises(NoMatchingRouteError) as exc_info:
        await router_component._run_without_io_trace(inputs, {})

    assert "3 route(s)" in str(exc_info.value)


@pytest.mark.asyncio
async def test_router_numeric_equality_exact(router_component):
    """Test router with numeric values - exact match"""
    output_data = {"numeric": "result"}
    inputs = RouterInputs(
        routes=[
            RouteCondition(value_a=1, value_b=2),
            RouteCondition(value_a=2, value_b=3),
            RouteCondition(value_a=5, value_b=5),  # Matches
            RouteCondition(value_a=10, value_b=11),
        ],
        output_data=output_data,
    )
    result = await router_component._run_without_io_trace(inputs, {})

    assert result._directive.selected_edge_indices == [2]
    assert result.output == output_data


@pytest.mark.asyncio
async def test_router_string_equality(router_component):
    """Test router with string equality"""
    output_data = "hello world"
    inputs = RouterInputs(
        routes=[
            RouteCondition(value_a="world", value_b="no_match"),
            RouteCondition(value_a="hello", value_b="hello"),  # Matches
            RouteCondition(value_a="foo", value_b="no_match"),
        ],
        output_data=output_data,
    )
    result = await router_component._run_without_io_trace(inputs, {})

    assert result._directive.selected_edge_indices == [1]
    assert result.output == output_data


@pytest.mark.asyncio
async def test_router_complex_data_comparison(router_component):
    """Test router compares complex data structures"""
    complex_data = {"key": "value", "nested": {"data": [1, 2, 3]}}
    output_data = {"output": "complex"}
    inputs = RouterInputs(
        routes=[
            RouteCondition(value_a="simple", value_b="no_match"),
            RouteCondition(value_a=complex_data, value_b=complex_data),  # Matches
            RouteCondition(value_a="other", value_b="no_match"),
        ],
        output_data=output_data,
    )
    result = await router_component._run_without_io_trace(inputs, {})

    assert result._directive.selected_edge_indices == [1]
    assert result.output == output_data


@pytest.mark.asyncio
async def test_router_empty_routes_list(router_component):
    """Test router with empty routes list - should raise error"""
    inputs = RouterInputs(routes=[], output_data={"test": "data"})

    with pytest.raises(NoMatchingRouteError):
        await router_component._run_without_io_trace(inputs, {})


@pytest.mark.asyncio
async def test_router_float_comparison(router_component):
    """Test router with float values"""
    output_data = 3.14159
    inputs = RouterInputs(
        routes=[
            RouteCondition(value_a=1.5, value_b=2.0),
            RouteCondition(value_a=2.7, value_b=3.0),
            RouteCondition(value_a=3.14, value_b=3.14),  # Matches
            RouteCondition(value_a=4.2, value_b=5.0),
        ],
        output_data=output_data,
    )
    result = await router_component._run_without_io_trace(inputs, {})

    assert result._directive.selected_edge_indices == [2]
    assert result.output == output_data


@pytest.mark.asyncio
async def test_router_mixed_type_routes(router_component):
    """Test router with mixed types in routes"""
    output_data = {"mixed": True}
    inputs = RouterInputs(
        routes=[
            RouteCondition(value_a=1, value_b=2),
            RouteCondition(value_a="hello", value_b="world"),
            RouteCondition(value_a="5", value_b="5"),  # Matches
            RouteCondition(value_a=True, value_b=False),
        ],
        output_data=output_data,
    )
    result = await router_component._run_without_io_trace(inputs, {})

    assert result._directive.selected_edge_indices == [2]
    assert result.output == output_data


@pytest.mark.asyncio
async def test_router_boolean_values(router_component):
    """Test router with boolean values"""
    output_data = True
    inputs = RouterInputs(
        routes=[
            RouteCondition(value_a=False, value_b=True),
            RouteCondition(value_a=True, value_b=True),  # Matches
            RouteCondition(value_a="true", value_b="false"),
        ],
        output_data=output_data,
    )
    result = await router_component._run_without_io_trace(inputs, {})

    assert result._directive.selected_edge_indices == [1]
    assert result.output == output_data


@pytest.mark.asyncio
async def test_router_none_value(router_component):
    """Test router with None as comparison value"""
    output_data = None
    inputs = RouterInputs(
        routes=[
            RouteCondition(value_a="test", value_b="no_match"),
            RouteCondition(value_a=None, value_b=None),  # Matches
            RouteCondition(value_a="other", value_b="no_match"),
        ],
        output_data=output_data,
    )
    result = await router_component._run_without_io_trace(inputs, {})

    assert result._directive.selected_edge_indices == [1]
    assert result.output == output_data


@pytest.mark.asyncio
async def test_router_list_value_comparison(router_component):
    """Test router with list as comparison value"""
    list_value = [1, 2, 3]
    output_data = ["output", "list"]
    inputs = RouterInputs(
        routes=[
            RouteCondition(value_a=[4, 5], value_b=[6, 7]),
            RouteCondition(value_a=list_value, value_b=list_value),  # Matches
            RouteCondition(value_a=[7, 8], value_b=[9, 10]),
        ],
        output_data=output_data,
    )
    result = await router_component._run_without_io_trace(inputs, {})

    assert result._directive.selected_edge_indices == [1]
    assert result.output == output_data


@pytest.mark.asyncio
async def test_router_dict_value_comparison(router_component):
    """Test router with dict as comparison value"""
    dict_value = {"a": 1, "b": 2}
    output_data = {"output": "dict"}
    inputs = RouterInputs(
        routes=[
            RouteCondition(value_a={"c": 3}, value_b={"d": 4}),
            RouteCondition(value_a=dict_value, value_b=dict_value),  # Matches
            RouteCondition(value_a={"d": 4}, value_b={"e": 5}),
        ],
        output_data=output_data,
    )
    result = await router_component._run_without_io_trace(inputs, {})

    assert result._directive.selected_edge_indices == [1]
    assert result.output == output_data


@pytest.mark.asyncio
async def test_router_case_sensitive_strings(router_component):
    """Test router is case sensitive for strings"""
    output_data = "Case Sensitive"
    inputs = RouterInputs(
        routes=[
            RouteCondition(value_a="hello", value_b="HELLO"),
            RouteCondition(value_a="HELLO", value_b="hello"),
            RouteCondition(value_a="Hello", value_b="Hello"),  # Matches
        ],
        output_data=output_data,
    )
    result = await router_component._run_without_io_trace(inputs, {})

    assert result._directive.selected_edge_indices == [2]
    assert result.output == output_data


@pytest.mark.asyncio
async def test_router_output_schema_structure(router_component):
    """Test that output schema has single output field"""
    OutputModel = router_component.get_outputs_schema()

    # Router has single output field
    assert "output" in OutputModel.model_fields


@pytest.mark.asyncio
async def test_router_input_schema_structure(router_component):
    """Test that input schema has correct structure"""
    InputModel = router_component.get_inputs_schema()
    fields = InputModel.model_fields

    assert "routes" in fields
    assert "output_data" in fields


def test_router_canonical_ports(router_component):
    """Test router canonical ports configuration"""
    canonical_ports = router_component.get_canonical_ports()

    assert canonical_ports["input"] == "routes"
    assert canonical_ports["output"] == "output"


@pytest.mark.asyncio
async def test_router_value_b_comparison(router_component):
    """Test router comparing value_a against value_b"""
    output_data = "banana split"
    inputs = RouterInputs(
        routes=[
            RouteCondition(value_a="apple", value_b="orange"),
            RouteCondition(value_a="banana", value_b="banana"),
            RouteCondition(value_a="cherry", value_b="grape"),
        ],
        output_data=output_data,
    )
    result = await router_component._run_without_io_trace(inputs, {})

    assert result._directive.selected_edge_indices == [1]
    assert result.output == output_data


@pytest.mark.asyncio
async def test_router_value_b_defaults_to_value_a(router_component):
    """Test router uses value_a when value_b is not provided (defaults to value_a, so always matches)"""
    output_data = "default match"
    inputs = RouterInputs(
        routes=[
            RouteCondition(value_a="apple"),  # value_b defaults to value_a, so matches
            RouteCondition(value_a="banana", value_b="cherry"),
        ],
        output_data=output_data,
    )
    result = await router_component._run_without_io_trace(inputs, {})

    # When value_b is None, it defaults to value_a, so route_0 matches
    assert result._directive.selected_edge_indices == [0]
    assert result.output == output_data


@pytest.mark.asyncio
async def test_router_multiple_routes_match(router_component):
    """Test router returns all matching routes and outputs data to each"""
    output_data = {"multi": "match"}
    inputs = RouterInputs(
        routes=[
            RouteCondition(value_a="match", value_b="match"),  # Matches
            RouteCondition(value_a="no", value_b="match"),  # Doesn't match
            RouteCondition(value_a="test", value_b="test"),  # Matches
        ],
        output_data=output_data,
    )
    result = await router_component._run_without_io_trace(inputs, {})

    # Router returns all matching routes
    assert 0 in result._directive.selected_edge_indices
    assert 2 in result._directive.selected_edge_indices
    assert len(result._directive.selected_edge_indices) == 2
    # Both matching routes should have output data
    assert result.output == output_data
    assert result.output == output_data


@pytest.mark.asyncio
async def test_router_directive_structure(router_component):
    """Test that router returns proper ExecutionDirective"""
    output_data = "directive test"
    inputs = RouterInputs(routes=[RouteCondition(value_a="test")], output_data=output_data)
    result = await router_component._run_without_io_trace(inputs, {})

    # Check directive exists and has correct structure
    assert hasattr(result, "_directive")
    assert result._directive is not None
    assert result._directive.strategy == ExecutionStrategy.SELECTIVE_EDGE_INDICES
    assert isinstance(result._directive.selected_edge_indices, list)
    assert all(isinstance(idx, int) for idx in result._directive.selected_edge_indices)
    # Check output data is present
    assert result.output == output_data
