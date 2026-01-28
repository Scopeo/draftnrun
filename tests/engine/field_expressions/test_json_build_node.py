"""Tests for JsonBuildNode field expression type."""

import pytest

from engine.components.types import NodeData
from engine.field_expressions.ast import JsonBuildNode, RefNode
from engine.field_expressions.serializer import from_json, to_json
from engine.graph_runner.field_expression_management import evaluate_expression
from engine.graph_runner.types import Task, TaskState


class TestJsonBuildNodeSerialization:
    """Test JsonBuildNode serialization and deserialization."""

    def test_to_json(self):
        """Test serializing JsonBuildNode to JSON."""
        node = JsonBuildNode(
            template=[{"value_a": "__REF_0__", "operator": "is_not_empty"}],
            refs={"__REF_0__": RefNode(instance="abc", port="messages")},
        )

        result = to_json(node)

        assert result == {
            "type": "json_build",
            "template": [{"value_a": "__REF_0__", "operator": "is_not_empty"}],
            "refs": {
                "__REF_0__": {
                    "type": "ref",
                    "instance": "abc",
                    "port": "messages",
                }
            },
        }

    def test_from_json(self):
        """Test deserializing JsonBuildNode from JSON."""
        json_data = {
            "type": "json_build",
            "template": [{"value_a": "__REF_0__", "operator": "is_not_empty"}],
            "refs": {
                "__REF_0__": {
                    "type": "ref",
                    "instance": "abc",
                    "port": "messages",
                }
            },
        }

        result = from_json(json_data)

        assert isinstance(result, JsonBuildNode)
        assert result.template == [{"value_a": "__REF_0__", "operator": "is_not_empty"}]
        assert "__REF_0__" in result.refs
        assert result.refs["__REF_0__"].instance == "abc"
        assert result.refs["__REF_0__"].port == "messages"

    def test_roundtrip(self):
        """Test serialization roundtrip."""
        original = JsonBuildNode(
            template={"key": "__PLACEHOLDER__"},
            refs={"__PLACEHOLDER__": RefNode(instance="comp1", port="output")},
        )

        json_data = to_json(original)
        restored = from_json(json_data)

        assert restored.template == original.template
        assert restored.refs["__PLACEHOLDER__"].instance == "comp1"
        assert restored.refs["__PLACEHOLDER__"].port == "output"


class TestJsonBuildNodeEvaluation:
    """Test JsonBuildNode evaluation in field expressions."""

    def test_simple_substitution(self):
        """Test simple placeholder substitution."""
        # Setup: Create a task with a list output
        tasks = {
            "upstream": Task(
                state=TaskState.COMPLETED,
                pending_deps=0,
                result=NodeData(
                    data={"messages": [{"role": "user", "content": "Hello"}]},
                    ctx={},
                ),
            )
        }

        # Create JsonBuildNode expression
        expression = JsonBuildNode(
            template=[{"value_a": "__MESSAGES__", "operator": "is_not_empty"}],
            refs={"__MESSAGES__": RefNode(instance="upstream", port="messages")},
        )

        # Evaluate
        result = evaluate_expression(expression, "test_field", tasks)

        # Verify: messages list is preserved as-is, not stringified
        assert result == [
            {
                "value_a": [{"role": "user", "content": "Hello"}],
                "operator": "is_not_empty",
            }
        ]
        assert isinstance(result, list)
        assert isinstance(result[0]["value_a"], list)

    def test_multiple_refs(self):
        """Test multiple placeholder substitutions."""
        tasks = {
            "comp1": Task(
                state=TaskState.COMPLETED,
                pending_deps=0,
                result=NodeData(data={"output": "value1"}, ctx={}),
            ),
            "comp2": Task(
                state=TaskState.COMPLETED,
                pending_deps=0,
                result=NodeData(data={"output": "value2"}, ctx={}),
            ),
        }

        expression = JsonBuildNode(
            template={"field_a": "__REF_1__", "field_b": "__REF_2__"},
            refs={
                "__REF_1__": RefNode(instance="comp1", port="output"),
                "__REF_2__": RefNode(instance="comp2", port="output"),
            },
        )

        result = evaluate_expression(expression, "test_field", tasks)

        assert result == {"field_a": "value1", "field_b": "value2"}

    def test_nested_structure(self):
        """Test nested template structure."""
        tasks = {
            "upstream": Task(
                state=TaskState.COMPLETED,
                pending_deps=0,
                result=NodeData(data={"config": {"model": "gpt-4"}}, ctx={}),
            )
        }

        expression = JsonBuildNode(
            template={
                "conditions": [
                    {"value_a": "__CONFIG__", "operator": "is_not_empty"},
                    {"value_a": "literal", "operator": "equals"},
                ]
            },
            refs={"__CONFIG__": RefNode(instance="upstream", port="config")},
        )

        result = evaluate_expression(expression, "test_field", tasks)

        assert result == {
            "conditions": [
                {"value_a": {"model": "gpt-4"}, "operator": "is_not_empty"},
                {"value_a": "literal", "operator": "equals"},
            ]
        }
        assert isinstance(result["conditions"][0]["value_a"], dict)

    def test_preserves_complex_types(self):
        """Test that complex Python types are preserved (not stringified)."""
        tasks = {
            "upstream": Task(
                state=TaskState.COMPLETED,
                pending_deps=0,
                result=NodeData(
                    data={
                        "output": [
                            {"role": "user", "content": "Test with apostrophe's"},
                            {"role": "assistant", "content": 'Test with "quotes"'},
                        ]
                    },
                    ctx={},
                ),
            )
        }

        expression = JsonBuildNode(
            template=[{"value_a": "__OUTPUT__", "operator": "is_not_empty"}],
            refs={"__OUTPUT__": RefNode(instance="upstream", port="output")},
        )

        result = evaluate_expression(expression, "test_field", tasks)

        # Verify the list is preserved with all special characters intact
        assert result == [
            {
                "value_a": [
                    {"role": "user", "content": "Test with apostrophe's"},
                    {"role": "assistant", "content": 'Test with "quotes"'},
                ],
                "operator": "is_not_empty",
            }
        ]
        # Verify it's actually a list, not a stringified version
        assert isinstance(result[0]["value_a"], list)
        assert result[0]["value_a"][0]["content"] == "Test with apostrophe's"

    def test_missing_task_raises_error(self):
        """Test that missing upstream task raises appropriate error."""
        tasks = {}

        expression = JsonBuildNode(
            template={"field": "__REF__"},
            refs={"__REF__": RefNode(instance="missing", port="output")},
        )

        with pytest.raises(Exception) as exc_info:
            evaluate_expression(expression, "test_field", tasks)

        assert "missing" in str(exc_info.value).lower()
