"""Test simple payload schema with field names and default values."""

import json
import pytest
import asyncio
from unittest.mock import MagicMock

from engine.agent.inputs_outputs.input import Input
from engine.agent.inputs_outputs.start import Start
from engine.agent.json_schema_utils import (
    extract_defaults_from_schema,
    parse_json_schema_string,
    validate_and_apply_defaults,
)
from engine.agent.types import ComponentAttributes, ToolDescription
from engine.trace.trace_manager import TraceManager


@pytest.fixture
def mock_trace_manager():
    return MagicMock(spec=TraceManager)


class TestJsonSchemaUtils:
    def test_extract_defaults_from_simple_schema(self):
        schema = {
            "type": "object",
            "properties": {
                "username": {"type": "string", "default": "John"},
                "age": {"type": "integer", "default": 30},
                "active": {"type": "boolean", "default": True},
            },
        }

        defaults = extract_defaults_from_schema(schema)

        assert defaults == {"username": "John", "age": 30, "active": True}

    def test_extract_defaults_from_schema_with_no_defaults(self):
        schema = {
            "type": "object",
            "properties": {"username": {"type": "string"}, "age": {"type": "integer"}},
        }

        defaults = extract_defaults_from_schema(schema)

        assert defaults == {}

    def test_extract_defaults_from_nested_object_schema(self):
        schema = {
            "type": "object",
            "properties": {
                "user": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "default": "John"},
                        "email": {"type": "string", "default": "john@example.com"},
                    },
                },
                "count": {"type": "integer", "default": 5},
            },
        }

        defaults = extract_defaults_from_schema(schema)

        assert defaults == {"user": {"name": "John", "email": "john@example.com"}, "count": 5}

    def test_parse_json_schema_string(self):
        schema_str = json.dumps({"type": "object", "properties": {"field": {"type": "string", "default": "value"}}})

        schema = parse_json_schema_string(schema_str)

        assert schema["type"] == "object"
        assert schema["properties"]["field"]["default"] == "value"

    def test_parse_invalid_json_raises_error(self):
        schema_str = "not valid json"

        with pytest.raises(json.JSONDecodeError):
            parse_json_schema_string(schema_str)

    def test_validate_and_apply_defaults(self):
        schema = {
            "type": "object",
            "properties": {
                "username": {"type": "string", "default": "Guest"},
                "age": {"type": "integer", "default": 18},
            },
        }

        data = {"username": "Alice"}
        result = validate_and_apply_defaults(data, schema)

        assert result == {"username": "Alice", "age": 18}


class TestSimplePayloadSchemaWithInput:
    def test_input_with_simple_payload_builder_schema(self, mock_trace_manager):
        # This simulates the schema output from the PayloadBuilder component
        # which outputs JSON Schema with type=object and properties with defaults
        schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {
                "messages": {"type": "array", "default": []},
                "user_name": {"type": "string", "default": "Guest"},
                "language": {"type": "string", "default": "en"},
            },
        }

        input_block = Input(
            trace_manager=mock_trace_manager,
            tool_description=ToolDescription(
                name="input", description="input", tool_properties={}, required_tool_properties=[]
            ),
            component_attributes=ComponentAttributes(component_instance_name="Test Input"),
            payload_schema=json.dumps(schema),
        )

        input_data = {"messages": [{"role": "user", "content": "hi"}], "user_name": "Alice"}
        result = asyncio.run(input_block.run(input_data))

        # Template vars should extract the defaults
        assert result.ctx.get("template_vars") == {
            "user_name": "Alice",
            "language": "en",
        }

    def test_start_with_simple_payload_builder_schema(self, mock_trace_manager):
        # This simulates the schema output from the PayloadBuilder component
        schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {
                "messages": {"type": "array", "default": []},
                "company": {"type": "string", "default": "Draft'n Run"},
                "year": {"type": "string", "default": "2025"},
            },
        }

        start_block = Start(
            trace_manager=mock_trace_manager,
            tool_description=ToolDescription(
                name="start", description="start", tool_properties={}, required_tool_properties=[]
            ),
            component_attributes=ComponentAttributes(component_instance_name="Test Start"),
            payload_schema=json.dumps(schema),
        )

        input_data = {"messages": [{"role": "user", "content": "hello"}]}
        result = asyncio.run(start_block.run(input_data))

        # Should apply defaults for missing fields
        assert result.ctx.get("template_vars") == {
            "company": "Draft'n Run",
            "year": "2025",
        }

    def test_payload_builder_schema_minimal(self, mock_trace_manager):
        # Minimal schema from PayloadBuilder - just field name and default value
        schema = {
            "type": "object",
            "properties": {
                "api_key": {"type": "string", "default": "test-key-123"},
                "timeout": {"type": "string", "default": "30"},
            },
        }

        input_block = Input(
            trace_manager=mock_trace_manager,
            tool_description=ToolDescription(
                name="input", description="input", tool_properties={}, required_tool_properties=[]
            ),
            component_attributes=ComponentAttributes(component_instance_name="Test Input"),
            payload_schema=json.dumps(schema),
        )

        # Empty input should get defaults applied
        input_data = {}
        result = asyncio.run(input_block.run(input_data))

        # Template vars should have the defaults
        assert result.ctx.get("template_vars") == {
            "api_key": "test-key-123",
            "timeout": "30",
        }
