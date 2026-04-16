from uuid import uuid4

import pytest

from ada_backend.schemas.pipeline.graph_schema import GraphSaveV2Schema
from ada_backend.services.graph.graph_v2_mapper_service import (
    _resolve_expression_file_keys,
    graph_save_v2_to_graph_update,
)


def test_v2_mapper_creates_ids_when_missing():
    comp_id = uuid4()
    comp_ver_id = uuid4()
    payload = GraphSaveV2Schema(
        graph_map={
            "nodes": [
                {
                    "file_key": "start",
                    "is_start_node": True,
                },
                {"file_key": "agent"},
            ],
            "edges": [
                {"from": {"file_key": "start"}, "to": {"file_key": "agent"}},
            ],
        },
        components=[
            {"file_key": "start", "component_id": comp_id, "component_version_id": comp_ver_id, "parameters": []},
            {"file_key": "agent", "component_id": comp_id, "component_version_id": comp_ver_id, "parameters": []},
        ],
    )

    result = graph_save_v2_to_graph_update(payload)
    assert len(result.component_instances) == 2
    assert all(instance.id for instance in result.component_instances)
    assert len(result.edges) == 1


def test_v2_mapper_raises_on_duplicate_node_file_key():
    comp_id = uuid4()
    comp_ver_id = uuid4()
    payload = GraphSaveV2Schema(
        graph_map={
            "nodes": [
                {"file_key": "start", "is_start_node": True},
                {"file_key": "start"},
            ],
            "edges": [],
        },
        components=[
            {"file_key": "start", "component_id": comp_id, "component_version_id": comp_ver_id, "parameters": []},
        ],
    )

    with pytest.raises(ValueError, match="Duplicate file_key 'start' in graph_map.nodes"):
        graph_save_v2_to_graph_update(payload)


def test_v2_mapper_raises_on_unknown_file_key_edge():
    comp_id = uuid4()
    comp_ver_id = uuid4()
    payload = GraphSaveV2Schema(
        graph_map={
            "nodes": [{"file_key": "start"}],
            "edges": [{"from": {"file_key": "start"}, "to": {"file_key": "missing"}}],
        },
        components=[
            {"file_key": "start", "component_id": comp_id, "component_version_id": comp_ver_id, "parameters": []}
        ],
    )

    with pytest.raises(ValueError, match="Unknown file_key"):
        graph_save_v2_to_graph_update(payload)


class TestResolveExpressionFileKeys:
    def test_ref_with_file_key_resolved(self):
        mapping = {"start": uuid4()}
        expr = {"type": "ref", "file_key": "start", "port": "output"}
        result = _resolve_expression_file_keys(expr, mapping)
        assert result == {"type": "ref", "instance": str(mapping["start"]), "port": "output"}
        assert "file_key" not in result

    def test_ref_with_instance_unchanged(self):
        instance_id = str(uuid4())
        expr = {"type": "ref", "instance": instance_id, "port": "output"}
        result = _resolve_expression_file_keys(expr, {})
        assert result is expr

    def test_ref_with_file_key_preserves_extra_keys(self):
        mapping = {"comp1": uuid4()}
        expr = {"type": "ref", "file_key": "comp1", "port": "output", "key": "messages"}
        result = _resolve_expression_file_keys(expr, mapping)
        assert result == {"type": "ref", "instance": str(mapping["comp1"]), "port": "output", "key": "messages"}

    def test_unknown_file_key_raises(self):
        with pytest.raises(ValueError, match="Unknown file_key 'missing'"):
            _resolve_expression_file_keys({"type": "ref", "file_key": "missing", "port": "out"}, {})

    def test_concat_resolves_nested_refs(self):
        mapping = {"a": uuid4(), "b": uuid4()}
        expr = {
            "type": "concat",
            "parts": [
                {"type": "ref", "file_key": "a", "port": "x"},
                {"type": "literal", "value": " + "},
                {"type": "ref", "file_key": "b", "port": "y"},
            ],
        }
        result = _resolve_expression_file_keys(expr, mapping)
        assert result["parts"][0] == {"type": "ref", "instance": str(mapping["a"]), "port": "x"}
        assert result["parts"][1] == {"type": "literal", "value": " + "}
        assert result["parts"][2] == {"type": "ref", "instance": str(mapping["b"]), "port": "y"}

    def test_json_build_resolves_nested_refs(self):
        mapping = {"comp": uuid4()}
        expr = {
            "type": "json_build",
            "fields": {
                "name": {"type": "ref", "file_key": "comp", "port": "name"},
                "static": {"type": "literal", "value": "hello"},
            },
        }
        result = _resolve_expression_file_keys(expr, mapping)
        assert result["fields"]["name"] == {"type": "ref", "instance": str(mapping["comp"]), "port": "name"}
        assert result["fields"]["static"] == {"type": "literal", "value": "hello"}

    def test_json_build_refs_format_resolves_nested_refs(self):
        mapping = {"comp": uuid4()}
        expr = {
            "type": "json_build",
            "template": [{"value_a": "__REF_0__", "operator": "is_not_empty"}],
            "refs": {
                "__REF_0__": {"type": "ref", "file_key": "comp", "port": "messages"},
            },
        }
        result = _resolve_expression_file_keys(expr, mapping)
        assert result["refs"]["__REF_0__"] == {
            "type": "ref", "instance": str(mapping["comp"]), "port": "messages"
        }
        assert result["template"] == expr["template"]

    def test_literal_unchanged(self):
        expr = {"type": "literal", "value": "hello"}
        result = _resolve_expression_file_keys(expr, {})
        assert result is expr


class TestMapperResolvesFieldExpressionFileKeys:
    def test_end_to_end_file_key_refs_resolved(self):
        comp_id = uuid4()
        comp_ver_id = uuid4()
        payload = GraphSaveV2Schema(
            graph_map={
                "nodes": [
                    {"file_key": "start", "is_start_node": True},
                    {"file_key": "scorer"},
                ],
                "edges": [{"from": {"file_key": "start"}, "to": {"file_key": "scorer"}}],
            },
            components=[
                {
                    "file_key": "start",
                    "component_id": comp_id,
                    "component_version_id": comp_ver_id,
                    "parameters": [],
                },
                {
                    "file_key": "scorer",
                    "component_id": comp_id,
                    "component_version_id": comp_ver_id,
                    "parameters": [],
                    "input_port_instances": [
                        {
                            "name": "input",
                            "field_expression": {
                                "expression_json": {"type": "ref", "file_key": "start", "port": "lead_text"},
                            },
                        }
                    ],
                },
            ],
        )

        result = graph_save_v2_to_graph_update(payload)
        start_id = result.component_instances[0].id
        scorer_ports = result.component_instances[1].input_port_instances
        assert len(scorer_ports) == 1
        resolved_expr = scorer_ports[0].field_expression.expression_json
        assert resolved_expr["type"] == "ref"
        assert resolved_expr["instance"] == str(start_id)
        assert resolved_expr["port"] == "lead_text"
        assert "file_key" not in resolved_expr
