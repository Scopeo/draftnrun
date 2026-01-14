import json
from unittest.mock import MagicMock

import pytest

from engine.components.table_lookup import (
    DEFAULT_TABLE_LOOKUP_TOOL_DESCRIPTION,
    TableLookup,
    TableLookupInputs,
    TableLookupOutputs,
)
from engine.components.types import ComponentAttributes
from engine.trace.trace_manager import TraceManager


@pytest.fixture
def mock_trace_manager():
    return MagicMock(spec=TraceManager)


@pytest.fixture
def table_mapping():
    return {"hello": "world", "yes": "confirmed", "no": "rejected", "1": "one", "true": "yes"}


@pytest.fixture
def table_lookup_component(mock_trace_manager, table_mapping):
    return TableLookup(
        trace_manager=mock_trace_manager,
        component_attributes=ComponentAttributes(component_instance_name="test_table_lookup"),
        table_mapping=json.dumps(table_mapping),
        default_value="unknown",
    )


def test_table_lookup_initialization(table_lookup_component, table_mapping):
    assert table_lookup_component._table_mapping == table_mapping
    assert table_lookup_component._default_value == "unknown"
    assert table_lookup_component.tool_description == DEFAULT_TABLE_LOOKUP_TOOL_DESCRIPTION


def test_table_lookup_initialization_with_empty_default(mock_trace_manager):
    table_lookup = TableLookup(
        trace_manager=mock_trace_manager,
        component_attributes=ComponentAttributes(component_instance_name="test_table_lookup"),
        table_mapping='{"a": "b"}',
        default_value="",
    )
    assert table_lookup._default_value == ""


def test_table_lookup_initialization_invalid_json(mock_trace_manager):
    with pytest.raises(ValueError, match="Invalid 'table_mapping' parameter"):
        TableLookup(
            trace_manager=mock_trace_manager,
            component_attributes=ComponentAttributes(component_instance_name="test_table_lookup"),
            table_mapping="not valid json",
            default_value="default",
        )


def test_table_lookup_initialization_non_dict_json(mock_trace_manager):
    with pytest.raises(ValueError, match="must be a JSON object/dictionary"):
        TableLookup(
            trace_manager=mock_trace_manager,
            component_attributes=ComponentAttributes(component_instance_name="test_table_lookup"),
            table_mapping='["array", "not", "dict"]',
            default_value="default",
        )


@pytest.mark.asyncio
async def test_table_lookup_exact_match(table_lookup_component):
    inputs = TableLookupInputs(lookup_key="hello")
    result = await table_lookup_component._run_without_io_trace(inputs, {})

    assert isinstance(result, TableLookupOutputs)
    assert result.lookup_value == "world"


@pytest.mark.asyncio
async def test_table_lookup_exact_match_all_keys(table_lookup_component):
    test_cases = [
        ("hello", "world"),
        ("yes", "confirmed"),
        ("no", "rejected"),
        ("1", "one"),
        ("true", "yes"),
    ]

    for lookup_key, expected_value in test_cases:
        inputs = TableLookupInputs(lookup_key=lookup_key)
        result = await table_lookup_component._run_without_io_trace(inputs, {})
        assert result.lookup_value == expected_value, f"Failed for key: {lookup_key}"


@pytest.mark.asyncio
async def test_table_lookup_no_match_returns_default(table_lookup_component):
    inputs = TableLookupInputs(lookup_key="unknown_key")
    result = await table_lookup_component._run_without_io_trace(inputs, {})

    assert result.lookup_value == "unknown"


@pytest.mark.asyncio
async def test_table_lookup_no_match_with_empty_default(mock_trace_manager, table_mapping):
    table_lookup = TableLookup(
        trace_manager=mock_trace_manager,
        component_attributes=ComponentAttributes(component_instance_name="test_table_lookup"),
        table_mapping=json.dumps(table_mapping),
        default_value="",
    )

    inputs = TableLookupInputs(lookup_key="unknown_key")
    result = await table_lookup._run_without_io_trace(inputs, {})

    assert result.lookup_value == ""


@pytest.mark.asyncio
async def test_table_lookup_empty_mapping_returns_default(mock_trace_manager):
    table_lookup = TableLookup(
        trace_manager=mock_trace_manager,
        component_attributes=ComponentAttributes(component_instance_name="test_table_lookup"),
        table_mapping="{}",
        default_value="fallback",
    )

    inputs = TableLookupInputs(lookup_key="any_key")
    result = await table_lookup._run_without_io_trace(inputs, {})

    assert result.lookup_value == "fallback"


@pytest.mark.asyncio
async def test_table_lookup_numeric_values(mock_trace_manager):
    table_lookup = TableLookup(
        trace_manager=mock_trace_manager,
        component_attributes=ComponentAttributes(component_instance_name="test_table_lookup"),
        table_mapping='{"one": 1, "two": 2, "pi": 3.14}',
        default_value="0",
    )

    test_cases = [
        ("one", "1"),
        ("two", "2"),
        ("pi", "3.14"),
    ]

    for lookup_key, expected_value in test_cases:
        inputs = TableLookupInputs(lookup_key=lookup_key)
        result = await table_lookup._run_without_io_trace(inputs, {})
        assert result.lookup_value == expected_value


@pytest.mark.asyncio
async def test_table_lookup_numeric_no_match(mock_trace_manager):
    table_lookup = TableLookup(
        trace_manager=mock_trace_manager,
        component_attributes=ComponentAttributes(component_instance_name="test_table_lookup"),
        table_mapping='{"one": 1, "two": 2}',
        default_value="0",
    )

    inputs = TableLookupInputs(lookup_key="three")
    result = await table_lookup._run_without_io_trace(inputs, {})
    assert result.lookup_value == "0"


@pytest.mark.asyncio
async def test_table_lookup_case_sensitive(mock_trace_manager):
    table_lookup = TableLookup(
        trace_manager=mock_trace_manager,
        component_attributes=ComponentAttributes(component_instance_name="test_table_lookup"),
        table_mapping='{"Hello": "World", "hello": "world"}',
        default_value="not_found",
    )

    # Test exact case match
    inputs = TableLookupInputs(lookup_key="Hello")
    result = await table_lookup._run_without_io_trace(inputs, {})
    assert result.lookup_value == "World"

    inputs = TableLookupInputs(lookup_key="hello")
    result = await table_lookup._run_without_io_trace(inputs, {})
    assert result.lookup_value == "world"

    # Test case mismatch returns default
    inputs = TableLookupInputs(lookup_key="HELLO")
    result = await table_lookup._run_without_io_trace(inputs, {})
    assert result.lookup_value == "not_found"


@pytest.mark.asyncio
async def test_table_lookup_boolean_values(mock_trace_manager):
    table_lookup = TableLookup(
        trace_manager=mock_trace_manager,
        component_attributes=ComponentAttributes(component_instance_name="test_table_lookup"),
        table_mapping='{"enabled": true, "disabled": false}',
        default_value="unknown",
    )

    inputs = TableLookupInputs(lookup_key="enabled")
    result = await table_lookup._run_without_io_trace(inputs, {})
    assert result.lookup_value == "True"

    inputs = TableLookupInputs(lookup_key="disabled")
    result = await table_lookup._run_without_io_trace(inputs, {})
    assert result.lookup_value == "False"


def test_table_lookup_get_canonical_ports():
    canonical_ports = TableLookup.get_canonical_ports()
    assert canonical_ports == {"input": "lookup_key", "output": "lookup_value"}


def test_table_lookup_schemas():
    assert TableLookup.get_inputs_schema() == TableLookupInputs
    assert TableLookup.get_outputs_schema() == TableLookupOutputs
