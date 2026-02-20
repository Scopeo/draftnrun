from unittest.mock import MagicMock

import pytest

from engine.components.errors import NoMatchingRouteError
from engine.components.router import MAX_ROUTER_ROUTES, RouteCondition, Router, RouterInputs
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
    inputs = RouterInputs(routes=[RouteCondition(value_a="bottle", output="bottle_output")])
    result = await router_component._run_without_io_trace(inputs, {})

    assert result.route_0 == "bottle_output"
    assert result._directive.strategy == ExecutionStrategy.SELECTIVE_PORTS
    assert result._directive.selected_ports == ["route_0"]


@pytest.mark.asyncio
async def test_router_single_route_no_match(router_component):
    """Test router with single route that doesn't match - should raise error"""
    inputs = RouterInputs(routes=[RouteCondition(value_a="bottle", value_b="water", output="test")])

    with pytest.raises(NoMatchingRouteError):
        await router_component._run_without_io_trace(inputs, {})


@pytest.mark.asyncio
async def test_router_multiple_routes_first_matches(router_component):
    """Test router with multiple routes where first matches"""
    inputs = RouterInputs(
        routes=[
            RouteCondition(value_a="bottle", output="bottle_output"),
            RouteCondition(value_a="cup", output="cup_output"),
            RouteCondition(value_a="water", output="water_output"),
        ],
    )
    result = await router_component._run_without_io_trace(inputs, {})

    assert result._directive.selected_ports == ["route_0"]
    assert result.route_0 == "bottle_output"
    assert result.route_1 is None
    assert result.route_2 is None


@pytest.mark.asyncio
async def test_router_multiple_routes_middle_matches(router_component):
    """Test router with multiple routes where middle route matches"""
    inputs = RouterInputs(
        routes=[
            RouteCondition(value_a="bottle", value_b="no_match", output="bottle_output"),
            RouteCondition(value_a="cup", output="cup_output"),
            RouteCondition(value_a="water", value_b="no_match", output="water_output"),
        ],
    )
    result = await router_component._run_without_io_trace(inputs, {})

    assert result._directive.selected_ports == ["route_1"]
    assert result.route_0 is None
    assert result.route_1 == "cup"
    assert result.route_2 is None


@pytest.mark.asyncio
async def test_router_multiple_routes_last_matches(router_component):
    """Test router with multiple routes where last route matches"""
    inputs = RouterInputs(
        routes=[
            RouteCondition(value_a="bottle", value_b="no_match", output="bottle_output"),
            RouteCondition(value_a="cup", value_b="no_match", output="cup_output"),
            RouteCondition(value_a="water", output="water_output"),
        ],
    )
    result = await router_component._run_without_io_trace(inputs, {})

    assert result._directive.selected_ports == ["route_2"]
    assert result.route_0 is None
    assert result.route_1 is None
    assert result.route_2 == "water"


@pytest.mark.asyncio
async def test_router_no_routes_match(router_component):
    """Test router when no routes match - should raise error"""
    inputs = RouterInputs(
        routes=[
            RouteCondition(value_a="bottle", value_b="no_match", output="bottle_output"),
            RouteCondition(value_a="cup", value_b="no_match", output="cup_output"),
            RouteCondition(value_a="water", value_b="no_match", output="water_output"),
        ],
    )

    with pytest.raises(NoMatchingRouteError) as exc_info:
        await router_component._run_without_io_trace(inputs, {})

    assert "3 route(s)" in str(exc_info.value)


@pytest.mark.asyncio
async def test_router_numeric_equality_exact(router_component):
    """Test router with numeric values - exact match"""
    inputs = RouterInputs(
        routes=[
            RouteCondition(value_a=1, value_b=2, output="output_1"),
            RouteCondition(value_a=2, value_b=3, output="output_2"),
            RouteCondition(value_a=5, output="output_5"),
            RouteCondition(value_a=10, value_b=11, output="output_10"),
        ],
    )
    result = await router_component._run_without_io_trace(inputs, {})

    assert result._directive.selected_ports == ["route_2"]
    assert result.route_2 == "output_5"
    assert result.route_2 == 5
    assert result.route_0 is None
    assert result.route_1 is None
    assert result.route_3 is None


@pytest.mark.asyncio
async def test_router_string_equality(router_component):
    """Test router with string equality"""
    inputs = RouterInputs(
        routes=[
            RouteCondition(value_a="world", value_b="no_match", output="world_output"),
            RouteCondition(value_a="hello", output="hello_output"),
            RouteCondition(value_a="foo", value_b="no_match", output="foo_output"),
        ],
    )
    result = await router_component._run_without_io_trace(inputs, {})

    assert result._directive.selected_ports == ["route_1"]
    assert result.route_1 == "hello_output"


@pytest.mark.asyncio
async def test_router_complex_data_passthrough(router_component):
    """Test router outputs complex data structures"""
    complex_data = {"key": "value", "nested": {"data": [1, 2, 3]}}
    inputs = RouterInputs(
        routes=[
            RouteCondition(value_a="simple", value_b="no_match", output="simple_output"),
            RouteCondition(value_a=complex_data, output=complex_data),
            RouteCondition(value_a="other", value_b="no_match", output="other_output"),
        ],
    )
    result = await router_component._run_without_io_trace(inputs, {})

    assert result._directive.selected_ports == ["route_1"]
    assert result.route_1 == complex_data


@pytest.mark.asyncio
async def test_router_empty_routes_list(router_component):
    """Test router with empty routes list - should raise error"""
    inputs = RouterInputs(routes=[])

    with pytest.raises(NoMatchingRouteError):
        await router_component._run_without_io_trace(inputs, {})


@pytest.mark.asyncio
async def test_router_float_comparison(router_component):
    """Test router with float values"""
    inputs = RouterInputs(
        routes=[
            RouteCondition(value_a=1.5, value_b=2.0, output="output_1"),
            RouteCondition(value_a=2.7, value_b=3.0, output="output_2"),
            RouteCondition(value_a=3.14, output="output_3.14"),
            RouteCondition(value_a=4.2, value_b=5.0, output="output_4"),
        ],
    )
    result = await router_component._run_without_io_trace(inputs, {})

    assert result._directive.selected_ports == ["route_2"]
    assert result.route_2 == "output_3.14"
    assert result.route_2 == 3.14


@pytest.mark.asyncio
async def test_router_mixed_type_routes(router_component):
    """Test router with mixed types in routes"""
    inputs = RouterInputs(
        routes=[
            RouteCondition(value_a=1, value_b=2, output="output_1"),
            RouteCondition(value_a="hello", value_b="world", output="output_hello"),
            RouteCondition(value_a="5", output="output_5"),
            RouteCondition(value_a=True, value_b=False, output="output_true"),
        ],
    )
    result = await router_component._run_without_io_trace(inputs, {})

    assert result._directive.selected_ports == ["route_2"]
    assert result.route_2 == "output_5"
    assert result.route_2 == "5"


@pytest.mark.asyncio
async def test_router_boolean_values(router_component):
    """Test router with boolean values"""
    inputs = RouterInputs(
        routes=[
            RouteCondition(value_a=False, value_b=True, output="false_output"),
            RouteCondition(value_a=True, output=True),
            RouteCondition(value_a="true", value_b="false", output="string_output"),
        ],
    )
    result = await router_component._run_without_io_trace(inputs, {})

    assert result._directive.selected_ports == ["route_1"]
    assert result.route_1 is True


@pytest.mark.asyncio
async def test_router_none_value(router_component):
    """Test router with None as comparison value"""
    inputs = RouterInputs(
        routes=[
            RouteCondition(value_a="test", value_b="no_match", output="test_output"),
            RouteCondition(value_a=None, output=None),
            RouteCondition(value_a="other", value_b="no_match", output="other_output"),
        ],
    )
    result = await router_component._run_without_io_trace(inputs, {})

    assert result._directive.selected_ports == ["route_1"]
    assert result.route_1 is None


@pytest.mark.asyncio
async def test_router_list_value_comparison(router_component):
    """Test router with list as comparison value"""
    list_value = [1, 2, 3]
    list_output = [10, 20, 30]
    inputs = RouterInputs(
        routes=[
            RouteCondition(value_a=[4, 5], value_b=[6, 7], output="output_1"),
            RouteCondition(value_a=list_value, output=list_output),
            RouteCondition(value_a=[7, 8], value_b=[9, 10], output="output_3"),
        ],
    )
    result = await router_component._run_without_io_trace(inputs, {})

    assert result._directive.selected_ports == ["route_1"]
    assert result.route_1 == list_output


@pytest.mark.asyncio
async def test_router_dict_value_comparison(router_component):
    """Test router with dict as comparison value"""
    dict_value = {"a": 1, "b": 2}
    dict_output = {"x": 10, "y": 20}
    inputs = RouterInputs(
        routes=[
            RouteCondition(value_a={"c": 3}, value_b={"d": 4}, output="output_1"),
            RouteCondition(value_a=dict_value, output=dict_output),
            RouteCondition(value_a={"d": 4}, value_b={"e": 5}, output="output_3"),
        ],
    )
    result = await router_component._run_without_io_trace(inputs, {})

    assert result._directive.selected_ports == ["route_1"]
    assert result.route_1 == dict_output


@pytest.mark.asyncio
async def test_router_case_sensitive_strings(router_component):
    """Test router is case sensitive for strings"""
    inputs = RouterInputs(
        routes=[
            RouteCondition(value_a="hello", value_b="HELLO", output="hello_output"),
            RouteCondition(value_a="HELLO", value_b="hello", output="HELLO_output"),
            RouteCondition(value_a="Hello", output="Hello_output"),
        ],
    )
    result = await router_component._run_without_io_trace(inputs, {})

    assert result._directive.selected_ports == ["route_2"]
    assert result.route_2 == "Hello_output"


@pytest.mark.asyncio
async def test_router_output_schema_structure(router_component):
    """Test that output schema has correct structure"""
    OutputModel = router_component.get_outputs_schema()
    fields = OutputModel.model_fields

    for i in range(MAX_ROUTER_ROUTES):
        assert f"route_{i}" in fields


@pytest.mark.asyncio
async def test_router_input_schema_structure(router_component):
    """Test that input schema has correct structure"""
    InputModel = router_component.get_inputs_schema()
    fields = InputModel.model_fields

    assert "routes" in fields


def test_router_canonical_ports(router_component):
    """Test router canonical ports configuration"""
    canonical_ports = router_component.get_canonical_ports()

    assert canonical_ports["input"] is None
    assert canonical_ports["output"] is None


@pytest.mark.asyncio
async def test_router_value_b_comparison(router_component):
    """Test router comparing value_a against value_b"""
    inputs = RouterInputs(
        routes=[
            RouteCondition(value_a="apple", value_b="orange", output="apple_output"),
            RouteCondition(value_a="banana", value_b="banana", output="banana_output"),
            RouteCondition(value_a="cherry", value_b="grape", output="cherry_output"),
        ],
    )
    result = await router_component._run_without_io_trace(inputs, {})

    assert result._directive.selected_ports == ["route_1"]
    assert result.route_1 == "banana_output"


@pytest.mark.asyncio
async def test_router_value_b_defaults_to_value_a(router_component):
    """Test router uses value_a when value_b is not provided"""
    inputs = RouterInputs(
        routes=[
            RouteCondition(value_a="apple", output="apple_output"),  # value_b defaults to value_a
            RouteCondition(value_a="banana", value_b="cherry", output="banana_output"),
        ],
    )
    result = await router_component._run_without_io_trace(inputs, {})

    assert result._directive.selected_ports == ["route_0"]
    assert result.route_0 == "apple_output"
