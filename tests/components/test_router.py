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
    inputs = RouterInputs(input="bottle", routes=[RouteCondition(value_a="bottle")])
    result = await router_component._run_without_io_trace(inputs, {})

    assert result.route_0 == "bottle"
    assert result._directive.strategy == ExecutionStrategy.SELECTIVE_PORTS
    assert result._directive.selected_ports == ["route_0"]


@pytest.mark.asyncio
async def test_router_single_route_no_match(router_component):
    """Test router with single route that doesn't match - should raise error"""
    inputs = RouterInputs(input="water", routes=[RouteCondition(value_a="bottle")])

    with pytest.raises(NoMatchingRouteError):
        await router_component._run_without_io_trace(inputs, {})


@pytest.mark.asyncio
async def test_router_multiple_routes_first_matches(router_component):
    """Test router with multiple routes where first matches"""
    inputs = RouterInputs(
        input="bottle",
        routes=[
            RouteCondition(value_a="bottle"),
            RouteCondition(value_a="cup"),
            RouteCondition(value_a="water"),
        ],
    )
    result = await router_component._run_without_io_trace(inputs, {})

    assert result._directive.selected_ports == ["route_0"]
    assert result.route_0 == "bottle"
    assert result.route_1 is None
    assert result.route_2 is None


@pytest.mark.asyncio
async def test_router_multiple_routes_middle_matches(router_component):
    """Test router with multiple routes where middle route matches"""
    inputs = RouterInputs(
        input="cup",
        routes=[
            RouteCondition(value_a="bottle"),
            RouteCondition(value_a="cup"),
            RouteCondition(value_a="water"),
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
        input="water",
        routes=[
            RouteCondition(value_a="bottle"),
            RouteCondition(value_a="cup"),
            RouteCondition(value_a="water"),
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
        input="juice",
        routes=[
            RouteCondition(value_a="bottle"),
            RouteCondition(value_a="cup"),
            RouteCondition(value_a="water"),
        ],
    )

    with pytest.raises(NoMatchingRouteError) as exc_info:
        await router_component._run_without_io_trace(inputs, {})

    assert "3 route(s)" in str(exc_info.value)


@pytest.mark.asyncio
async def test_router_numeric_equality_exact(router_component):
    """Test router with numeric values - exact match"""
    inputs = RouterInputs(
        input=5,
        routes=[
            RouteCondition(value_a=1),
            RouteCondition(value_a=2),
            RouteCondition(value_a=5),
            RouteCondition(value_a=10),
        ],
    )
    result = await router_component._run_without_io_trace(inputs, {})

    assert result._directive.selected_ports == ["route_2"]
    assert result.route_2 == 5
    assert result.route_0 is None
    assert result.route_1 is None
    assert result.route_3 is None


@pytest.mark.asyncio
async def test_router_string_equality(router_component):
    """Test router with string equality"""
    inputs = RouterInputs(
        input="hello",
        routes=[
            RouteCondition(value_a="world"),
            RouteCondition(value_a="hello"),
            RouteCondition(value_a="foo"),
        ],
    )
    result = await router_component._run_without_io_trace(inputs, {})

    assert result._directive.selected_ports == ["route_1"]
    assert result.route_1 == "hello"


@pytest.mark.asyncio
async def test_router_complex_data_passthrough(router_component):
    """Test router passes through complex data structures"""
    complex_data = {"key": "value", "nested": {"data": [1, 2, 3]}}
    inputs = RouterInputs(
        input=complex_data,
        routes=[
            RouteCondition(value_a="simple"),
            RouteCondition(value_a=complex_data),
            RouteCondition(value_a="other"),
        ],
    )
    result = await router_component._run_without_io_trace(inputs, {})

    assert result._directive.selected_ports == ["route_1"]
    assert result.route_1 == complex_data


@pytest.mark.asyncio
async def test_router_empty_routes_list(router_component):
    """Test router with empty routes list - should raise error"""
    inputs = RouterInputs(input="test", routes=[])

    with pytest.raises(NoMatchingRouteError):
        await router_component._run_without_io_trace(inputs, {})


@pytest.mark.asyncio
async def test_router_float_comparison(router_component):
    """Test router with float values"""
    inputs = RouterInputs(
        input=3.14,
        routes=[
            RouteCondition(value_a=1.5),
            RouteCondition(value_a=2.7),
            RouteCondition(value_a=3.14),
            RouteCondition(value_a=4.2),
        ],
    )
    result = await router_component._run_without_io_trace(inputs, {})

    assert result._directive.selected_ports == ["route_2"]
    assert result.route_2 == 3.14


@pytest.mark.asyncio
async def test_router_mixed_type_routes(router_component):
    """Test router with mixed types in routes"""
    inputs = RouterInputs(
        input="5",
        routes=[
            RouteCondition(value_a=1),
            RouteCondition(value_a="hello"),
            RouteCondition(value_a="5"),
            RouteCondition(value_a=True),
        ],
    )
    result = await router_component._run_without_io_trace(inputs, {})

    assert result._directive.selected_ports == ["route_2"]
    assert result.route_2 == "5"


@pytest.mark.asyncio
async def test_router_boolean_values(router_component):
    """Test router with boolean values"""
    inputs = RouterInputs(
        input=True,
        routes=[
            RouteCondition(value_a=False),
            RouteCondition(value_a=True),
            RouteCondition(value_a="true"),
        ],
    )
    result = await router_component._run_without_io_trace(inputs, {})

    assert result._directive.selected_ports == ["route_1"]
    assert result.route_1 is True


@pytest.mark.asyncio
async def test_router_none_value(router_component):
    """Test router with None as input value"""
    inputs = RouterInputs(
        input=None,
        routes=[
            RouteCondition(value_a="test"),
            RouteCondition(value_a=None),
            RouteCondition(value_a="other"),
        ],
    )
    result = await router_component._run_without_io_trace(inputs, {})

    assert result._directive.selected_ports == ["route_1"]


@pytest.mark.asyncio
async def test_router_list_value_comparison(router_component):
    """Test router with list as input value"""
    list_value = [1, 2, 3]
    inputs = RouterInputs(
        input=list_value,
        routes=[
            RouteCondition(value_a=[4, 5]),
            RouteCondition(value_a=list_value),
            RouteCondition(value_a=[7, 8]),
        ],
    )
    result = await router_component._run_without_io_trace(inputs, {})

    assert result._directive.selected_ports == ["route_1"]
    assert result.route_1 == list_value


@pytest.mark.asyncio
async def test_router_dict_value_comparison(router_component):
    """Test router with dict as input value"""
    dict_value = {"a": 1, "b": 2}
    inputs = RouterInputs(
        input=dict_value,
        routes=[
            RouteCondition(value_a={"c": 3}),
            RouteCondition(value_a=dict_value),
            RouteCondition(value_a={"d": 4}),
        ],
    )
    result = await router_component._run_without_io_trace(inputs, {})

    assert result._directive.selected_ports == ["route_1"]
    assert result.route_1 == dict_value


@pytest.mark.asyncio
async def test_router_case_sensitive_strings(router_component):
    """Test router is case sensitive for strings"""
    inputs = RouterInputs(
        input="Hello",
        routes=[
            RouteCondition(value_a="hello"),
            RouteCondition(value_a="HELLO"),
            RouteCondition(value_a="Hello"),
        ],
    )
    result = await router_component._run_without_io_trace(inputs, {})

    assert result._directive.selected_ports == ["route_2"]
    assert result.route_2 == "Hello"


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

    assert "input" in fields
    assert "routes" in fields


def test_router_canonical_ports(router_component):
    """Test router canonical ports configuration"""
    canonical_ports = router_component.get_canonical_ports()

    assert canonical_ports["input"] == "input"
    assert canonical_ports["output"] is None


@pytest.mark.asyncio
async def test_router_value_b_comparison(router_component):
    """Test router comparing value_a against value_b"""
    inputs = RouterInputs(
        input="test_data",
        routes=[
            RouteCondition(value_a="apple", value_b="orange"),
            RouteCondition(value_a="banana", value_b="banana"),
            RouteCondition(value_a="cherry", value_b="grape"),
        ],
    )
    result = await router_component._run_without_io_trace(inputs, {})

    assert result._directive.selected_ports == ["route_1"]
    assert result.route_1 == "test_data"


@pytest.mark.asyncio
async def test_router_value_b_defaults_to_value_a(router_component):
    """Test router uses value_a when value_b is not provided"""
    inputs = RouterInputs(
        input="test_data",
        routes=[
            RouteCondition(value_a="apple"),  # value_b defaults to value_a
            RouteCondition(value_a="banana"),
        ],
    )
    result = await router_component._run_without_io_trace(inputs, {})

    assert result._directive.selected_ports == ["route_0"]
    assert result.route_0 == "test_data"
