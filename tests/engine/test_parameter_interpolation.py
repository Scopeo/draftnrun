"""
Tests for Parameter Interpolation System

Validates the parsing and resolution of template strings with component output references.
"""

import pytest
from engine.graph_runner.parameter_interpolation import (
    ParameterInterpolator,
    TextSegment,
    ReferenceSegment,
)


class TestIsTemplate:
    """Test template detection."""

    def test_detects_simple_reference(self):
        assert ParameterInterpolator.is_template("{{@node1.output}}")

    def test_detects_mixed_template(self):
        assert ParameterInterpolator.is_template("Hello {{@node1.name}}!")

    def test_detects_multiple_references(self):
        assert ParameterInterpolator.is_template("{{@a.x}} and {{@b.y}}")

    def test_ignores_plain_text(self):
        assert not ParameterInterpolator.is_template("plain text")

    def test_ignores_escaped_braces(self):
        assert not ParameterInterpolator.is_template("\\{\\{not a reference}}")

    def test_ignores_non_strings(self):
        assert not ParameterInterpolator.is_template(123)
        assert not ParameterInterpolator.is_template(None)
        assert not ParameterInterpolator.is_template({"key": "value"})


class TestParseTemplate:
    """Test template parsing into segments."""

    def test_parse_simple_reference(self):
        segments = ParameterInterpolator.parse_template("{{@node1.output}}")
        assert len(segments) == 1
        assert isinstance(segments[0], ReferenceSegment)
        assert segments[0].node_id == "node1"
        assert segments[0].port_name == "output"

    def test_parse_text_only(self):
        segments = ParameterInterpolator.parse_template("plain text")
        assert len(segments) == 1
        assert isinstance(segments[0], TextSegment)
        assert segments[0].value == "plain text"

    def test_parse_mixed_template(self):
        segments = ParameterInterpolator.parse_template("Hello {{@agent1.name}}, welcome!")
        assert len(segments) == 3
        assert isinstance(segments[0], TextSegment)
        assert segments[0].value == "Hello "
        assert isinstance(segments[1], ReferenceSegment)
        assert segments[1].node_id == "agent1"
        assert segments[1].port_name == "name"
        assert isinstance(segments[2], TextSegment)
        assert segments[2].value == ", welcome!"

    def test_parse_multiple_references(self):
        segments = ParameterInterpolator.parse_template("{{@a.x}} and {{@b.y}}")
        assert len(segments) == 3
        assert isinstance(segments[0], ReferenceSegment)
        assert segments[0].node_id == "a"
        assert segments[0].port_name == "x"
        assert isinstance(segments[1], TextSegment)
        assert segments[1].value == " and "
        assert isinstance(segments[2], ReferenceSegment)
        assert segments[2].node_id == "b"
        assert segments[2].port_name == "y"

    def test_parse_escaped_braces(self):
        segments = ParameterInterpolator.parse_template("Use \\{\\{ for literal braces")
        assert len(segments) == 1
        assert isinstance(segments[0], TextSegment)
        assert segments[0].value == "Use {{ for literal braces"

    def test_parse_complex_ids(self):
        """Test parsing with complex node and port names."""
        segments = ParameterInterpolator.parse_template("{{@node-id_123.port_name-2}}")
        assert len(segments) == 1
        assert isinstance(segments[0], ReferenceSegment)
        assert segments[0].node_id == "node-id_123"
        assert segments[0].port_name == "port_name-2"


class TestExtractReferences:
    """Test reference extraction for dependency tracking."""

    def test_extract_single_reference(self):
        refs = ParameterInterpolator.extract_references("{{@node1.output}}")
        assert refs == [("node1", "output")]

    def test_extract_multiple_references(self):
        refs = ParameterInterpolator.extract_references("{{@a.x}} text {{@b.y}} more {{@c.z}}")
        assert refs == [("a", "x"), ("b", "y"), ("c", "z")]

    def test_extract_no_references(self):
        refs = ParameterInterpolator.extract_references("plain text")
        assert refs == []

    def test_extract_duplicate_references(self):
        """Same reference used multiple times."""
        refs = ParameterInterpolator.extract_references("{{@a.x}} and {{@a.x}} again")
        assert refs == [("a", "x"), ("a", "x")]


class TestResolveTemplate:
    """Test template resolution with actual values."""

    def test_resolve_simple_reference(self):
        """Single reference should return the value directly (preserve type)."""
        outputs = {"node1": {"output": "Hello World"}}
        result = ParameterInterpolator.resolve_template("{{@node1.output}}", outputs)
        assert result == "Hello World"

    def test_resolve_preserves_type_for_single_reference(self):
        """Single reference to dict/list should not stringify."""
        outputs = {"node1": {"data": {"key": "value", "num": 42}}}
        result = ParameterInterpolator.resolve_template("{{@node1.data}}", outputs)
        assert result == {"key": "value", "num": 42}
        assert isinstance(result, dict)

        outputs = {"node1": {"items": [1, 2, 3]}}
        result = ParameterInterpolator.resolve_template("{{@node1.items}}", outputs)
        assert result == [1, 2, 3]
        assert isinstance(result, list)

    def test_resolve_mixed_template(self):
        """Mixed text and reference should stringify."""
        outputs = {"agent1": {"name": "Alice"}}
        result = ParameterInterpolator.resolve_template("Hello {{@agent1.name}}!", outputs)
        assert result == "Hello Alice!"

    def test_resolve_multiple_references(self):
        outputs = {"calc": {"value": 42, "status": "ok"}}
        result = ParameterInterpolator.resolve_template("Result: {{@calc.value}} (status: {{@calc.status}})", outputs)
        assert result == "Result: 42 (status: ok)"

    def test_resolve_with_different_types(self):
        """Numbers, bools, etc. should be converted to strings when mixed."""
        outputs = {"node1": {"count": 5, "active": True, "score": 3.14}}
        result = ParameterInterpolator.resolve_template(
            "Count: {{@node1.count}}, Active: {{@node1.active}}, Score: {{@node1.score}}", outputs
        )
        assert result == "Count: 5, Active: True, Score: 3.14"

    def test_resolve_with_none(self):
        """None values should become empty strings when mixed."""
        outputs = {"node1": {"value": None}}
        result = ParameterInterpolator.resolve_template("Value: {{@node1.value}}", outputs)
        assert result == "Value: "

    def test_resolve_escaped_braces(self):
        """Escaped braces should become literal braces."""
        outputs = {}
        result = ParameterInterpolator.resolve_template("Use \\{\\{ for literal braces", outputs)
        assert result == "Use {{ for literal braces"

    def test_resolve_missing_node(self):
        """Should raise error if node doesn't exist."""
        outputs = {"node1": {"output": "value"}}
        with pytest.raises(ValueError, match="Component 'node2' not found"):
            ParameterInterpolator.resolve_template("{{@node2.output}}", outputs)

    def test_resolve_missing_port(self):
        """Should raise error if port doesn't exist."""
        outputs = {"node1": {"output": "value"}}
        with pytest.raises(ValueError, match="Port 'missing' not found"):
            ParameterInterpolator.resolve_template("{{@node1.missing}}", outputs)

    def test_resolve_non_template(self):
        """Non-templates should pass through unchanged."""
        outputs = {}
        result = ParameterInterpolator.resolve_template("plain text", outputs)
        assert result == "plain text"

        result = ParameterInterpolator.resolve_template(123, outputs)
        assert result == 123


class TestValueToString:
    """Test value conversion to strings for concatenation."""

    def test_stringify_dict(self):
        value = {"key": "value", "num": 42}
        result = ParameterInterpolator._value_to_string(value)
        assert result == '{"key": "value", "num": 42}'

    def test_stringify_list(self):
        value = [1, 2, 3, "test"]
        result = ParameterInterpolator._value_to_string(value)
        assert result == '[1, 2, 3, "test"]'

    def test_stringify_none(self):
        result = ParameterInterpolator._value_to_string(None)
        assert result == ""

    def test_stringify_primitives(self):
        assert ParameterInterpolator._value_to_string(42) == "42"
        assert ParameterInterpolator._value_to_string(3.14) == "3.14"
        assert ParameterInterpolator._value_to_string(True) == "True"
        assert ParameterInterpolator._value_to_string("text") == "text"


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_empty_template(self):
        segments = ParameterInterpolator.parse_template("")
        # Empty string produces empty segment list (no text to add)
        assert len(segments) == 0

    def test_only_escaped_braces(self):
        result = ParameterInterpolator.resolve_template("\\{\\{\\{\\{", {})
        assert result == "{{{{"

    def test_adjacent_references(self):
        """Two references with no text between them."""
        outputs = {"a": {"x": "foo"}, "b": {"y": "bar"}}
        result = ParameterInterpolator.resolve_template("{{@a.x}}{{@b.y}}", outputs)
        assert result == "foobar"

    def test_reference_at_start(self):
        outputs = {"node1": {"value": "start"}}
        result = ParameterInterpolator.resolve_template("{{@node1.value}} text", outputs)
        assert result == "start text"

    def test_reference_at_end(self):
        outputs = {"node1": {"value": "end"}}
        result = ParameterInterpolator.resolve_template("text {{@node1.value}}", outputs)
        assert result == "text end"

    def test_unicode_in_values(self):
        """Unicode characters should be preserved."""
        outputs = {"node1": {"text": "Hello 世界 🌍"}}
        result = ParameterInterpolator.resolve_template("Message: {{@node1.text}}", outputs)
        assert result == "Message: Hello 世界 🌍"
