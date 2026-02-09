from unittest.mock import MagicMock

import pytest

from engine.components.router import Router, RouterInputs, RouteCondition
from engine.components.types import ComponentAttributes
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

    assert result.matched_route_index == 0
    assert result.route_0 is not None
    assert result.route_0["data"] == "bottle"
    assert result.route_0["should_halt"] is False


@pytest.mark.asyncio
async def test_router_single_route_no_match(router_component):
    """Test router with single route that doesn't match"""
    inputs = RouterInputs(input="water", routes=[RouteCondition(value_a="bottle")])
    result = await router_component._run_without_io_trace(inputs, {})

    assert result.matched_route_index == -1
    assert result.route_0 is not None
    assert result.route_0["data"] is None
    assert result.route_0["should_halt"] is True


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

    assert result.matched_route_index == 0
    # Route 0 should be active
    assert result.route_0["data"] == "bottle"
    assert result.route_0["should_halt"] is False
    # Routes 1 and 2 should be halted
    assert result.route_1["data"] is None
    assert result.route_1["should_halt"] is True
    assert result.route_2["data"] is None
    assert result.route_2["should_halt"] is True


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

    assert result.matched_route_index == 1
    # Route 0 should be halted
    assert result.route_0["data"] is None
    assert result.route_0["should_halt"] is True
    # Route 1 should be active
    assert result.route_1["data"] == "cup"
    assert result.route_1["should_halt"] is False
    # Route 2 should be halted
    assert result.route_2["data"] is None
    assert result.route_2["should_halt"] is True


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

    assert result.matched_route_index == 2
    # Routes 0 and 1 should be halted
    assert result.route_0["should_halt"] is True
    assert result.route_1["should_halt"] is True
    # Route 2 should be active
    assert result.route_2["data"] == "water"
    assert result.route_2["should_halt"] is False


@pytest.mark.asyncio
async def test_router_no_routes_match(router_component):
    """Test router when no routes match - all should halt"""
    inputs = RouterInputs(
        input="juice",
        routes=[
            RouteCondition(value_a="bottle"),
            RouteCondition(value_a="cup"),
            RouteCondition(value_a="water"),
        ],
    )
    result = await router_component._run_without_io_trace(inputs, {})

    assert result.matched_route_index == -1
    # All routes should be halted
    assert result.route_0["should_halt"] is True
    assert result.route_1["should_halt"] is True
    assert result.route_2["should_halt"] is True


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

    assert result.matched_route_index == 2
    assert result.route_2["data"] == 5
    assert result.route_2["should_halt"] is False
    # Other routes should be halted
    assert result.route_0["should_halt"] is True
    assert result.route_1["should_halt"] is True
    assert result.route_3["should_halt"] is True


@pytest.mark.asyncio
async def test_router_numeric_string_coercion(router_component):
    """Test router with numeric string that should match number"""
    inputs = RouterInputs(
        input="5",
        routes=[
            RouteCondition(value_a=1),
            RouteCondition(value_a=2),
            RouteCondition(value_a=5),
            RouteCondition(value_a=10),
        ],
    )
    result = await router_component._run_without_io_trace(inputs, {})

    assert result.matched_route_index == 2
    assert result.route_2["data"] == "5"
    assert result.route_2["should_halt"] is False


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

    assert result.matched_route_index == 1
    assert result.route_1["data"] == "hello"
    assert result.route_1["should_halt"] is False


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

    assert result.matched_route_index == 1
    assert result.route_1["data"] == complex_data
    assert result.route_1["should_halt"] is False


@pytest.mark.asyncio
async def test_router_empty_routes_list(router_component):
    """Test router with empty routes list"""
    inputs = RouterInputs(input="test", routes=[])
    result = await router_component._run_without_io_trace(inputs, {})

    assert result.matched_route_index == -1


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

    assert result.matched_route_index == 2
    assert result.route_2["data"] == 3.14
    assert result.route_2["should_halt"] is False


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

    # Should match the string "5"
    assert result.matched_route_index == 2
    assert result.route_2["data"] == "5"
    assert result.route_2["should_halt"] is False


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

    assert result.matched_route_index == 1
    assert result.route_1["data"] is True
    assert result.route_1["should_halt"] is False


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

    assert result.matched_route_index == 1
    assert result.route_1["data"] is None
    assert result.route_1["should_halt"] is False


@pytest.mark.asyncio
async def test_router_max_routes(router_component):
    """Test router with maximum supported routes"""
    from engine.components.router import MAX_ROUTES

    routes = [RouteCondition(value_a=i) for i in range(MAX_ROUTES)]
    inputs = RouterInputs(input=5, routes=routes)
    result = await router_component._run_without_io_trace(inputs, {})

    assert result.matched_route_index == 5
    assert result.route_5["data"] == 5
    assert result.route_5["should_halt"] is False


@pytest.mark.asyncio
async def test_router_too_many_routes_raises_error(router_component):
    """Test router raises error when too many routes are provided"""
    from engine.components.router import MAX_ROUTES

    routes = [RouteCondition(value_a=i) for i in range(MAX_ROUTES + 1)]
    inputs = RouterInputs(input=5, routes=routes)

    with pytest.raises(ValueError, match=f"Router supports maximum {MAX_ROUTES} routes"):
        await router_component._run_without_io_trace(inputs, {})


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

    assert result.matched_route_index == 1
    assert result.route_1["data"] == list_value
    assert result.route_1["should_halt"] is False


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

    assert result.matched_route_index == 1
    assert result.route_1["data"] == dict_value
    assert result.route_1["should_halt"] is False


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

    assert result.matched_route_index == 2
    assert result.route_2["data"] == "Hello"
    assert result.route_2["should_halt"] is False


@pytest.mark.asyncio
async def test_router_output_schema_structure(router_component):
    """Test that output schema has correct structure"""
    OutputModel = router_component.get_outputs_schema()
    fields = OutputModel.model_fields

    assert "matched_route_index" in fields
    for i in range(20):  # MAX_ROUTES
        assert f"route_{i}" in fields


@pytest.mark.asyncio
async def test_router_input_schema_structure(router_component):
    """Test that input schema has correct structure"""
    InputModel = router_component.get_inputs_schema()
    fields = InputModel.model_fields

    assert "input_value" in fields
    assert "routes" in fields


def test_router_canonical_ports(router_component):
    """Test router canonical ports configuration"""
    canonical_ports = router_component.get_canonical_ports()

    assert canonical_ports["input"] == "input_value"
    assert canonical_ports["output"] is None  # Router has multiple outputs, no single canonical
