from uuid import UUID

from mcp_server.tools.graphs import _assign_missing_ids, _strip_readonly_messages_overrides, _warn_unknown_graph_keys


def test_assigns_uuids_to_null_id_instances():
    graph_data = {
        "component_instances": [
            {"id": None, "name": "A", "parameters": []},
            {"id": "existing-uuid", "name": "B", "parameters": []},
            {"id": None, "name": "C", "parameters": []},
        ],
        "edges": [],
    }

    result = _assign_missing_ids(graph_data)

    a_id = result["component_instances"][0]["id"]
    b_id = result["component_instances"][1]["id"]
    c_id = result["component_instances"][2]["id"]

    UUID(a_id)  # valid UUID
    UUID(c_id)  # valid UUID
    assert b_id == "existing-uuid"
    assert a_id != c_id


def test_assigns_uuids_to_null_id_edges():
    graph_data = {
        "component_instances": [{"id": "a"}, {"id": "b"}],
        "edges": [
            {"id": None, "origin": "a", "destination": "b", "order": 0},
            {"id": "existing-edge", "origin": "a", "destination": "b", "order": 1},
        ],
    }

    result = _assign_missing_ids(graph_data)

    edge_0_id = result["edges"][0]["id"]
    edge_1_id = result["edges"][1]["id"]

    UUID(edge_0_id)
    assert edge_1_id == "existing-edge"


def test_no_op_when_all_ids_present():
    graph_data = {
        "component_instances": [
            {"id": "aaa", "name": "A"},
            {"id": "bbb", "name": "B"},
        ],
    }

    result = _assign_missing_ids(graph_data)

    assert result["component_instances"][0]["id"] == "aaa"
    assert result["component_instances"][1]["id"] == "bbb"


def test_no_op_when_no_instances():
    assert _assign_missing_ids({}) == {}
    assert _assign_missing_ids({"component_instances": []}) == {"component_instances": []}


# --- _warn_unknown_graph_keys ---


def test_warns_on_typo_key():
    graph_data = {
        "component_instances": [],
        "edges": [],
        "ports_mappings": [],  # typo
    }
    warnings = _warn_unknown_graph_keys(graph_data)
    assert len(warnings) == 1
    assert "port_mappings" in warnings[0]
    assert "did you mean" in warnings[0].lower()


def test_no_warning_on_valid_keys():
    graph_data = {
        "component_instances": [],
        "edges": [],
        "port_mappings": [],
        "relationships": [],
    }
    assert _warn_unknown_graph_keys(graph_data) == []


def test_warns_on_completely_unknown_key():
    graph_data = {
        "component_instances": [],
        "edges": [],
        "something_random": True,
    }
    warnings = _warn_unknown_graph_keys(graph_data)
    assert len(warnings) == 1
    assert "something_random" in warnings[0]


# --- _strip_readonly_messages_overrides ---


def _make_graph(instances, edges):
    return {"component_instances": instances, "edges": edges}


def test_strips_messages_input_port_instance_on_edge_destination():
    graph = _make_graph(
        instances=[
            {"id": "start-1", "is_start_node": True, "parameters": [], "input_port_instances": []},
            {
                "id": "agent-1",
                "name": "My Agent",
                "parameters": [],
                "input_port_instances": [
                    {"name": "messages", "field_expression": {"expression_json": {"type": "literal", "value": "hi"}}},
                    {"name": "initial_prompt", "field_expression": {"expression_json": {
                        "type": "literal",
                        "value": "sys"
                        }}},
                ],
            },
        ],
        edges=[{"id": "e1", "origin": "start-1", "destination": "agent-1"}],
    )

    warnings = _strip_readonly_messages_overrides(graph)

    agent = graph["component_instances"][1]
    assert len(agent["input_port_instances"]) == 1
    assert agent["input_port_instances"][0]["name"] == "initial_prompt"
    assert len(warnings) == 1
    assert "messages" in warnings[0]
    assert "My Agent" in warnings[0]


def test_strips_messages_kind_input_parameter_on_edge_destination():
    graph = _make_graph(
        instances=[
            {"id": "start-1", "is_start_node": True, "parameters": [], "input_port_instances": []},
            {
                "id": "agent-1",
                "name": "Agent",
                "parameters": [
                    {"name": "messages", "kind": "input", "value": "override"},
                    {"name": "model_name", "kind": "parameter", "value": "gpt-4o"},
                ],
                "input_port_instances": [],
            },
        ],
        edges=[{"id": "e1", "origin": "start-1", "destination": "agent-1"}],
    )

    warnings = _strip_readonly_messages_overrides(graph)

    agent = graph["component_instances"][1]
    assert len(agent["parameters"]) == 1
    assert agent["parameters"][0]["name"] == "model_name"
    assert len(warnings) == 1


def test_no_strip_on_start_node():
    graph = _make_graph(
        instances=[
            {
                "id": "start-1",
                "is_start_node": True,
                "parameters": [{"name": "messages", "kind": "input", "value": "hi"}],
                "input_port_instances": [{"name": "messages", "field_expression": {}}],
            },
            {"id": "other-1", "parameters": [], "input_port_instances": []},
        ],
        edges=[{"id": "e1", "origin": "start-1", "destination": "other-1"}],
    )

    warnings = _strip_readonly_messages_overrides(graph)

    start = graph["component_instances"][0]
    assert len(start["parameters"]) == 1
    assert len(start["input_port_instances"]) == 1
    assert warnings == []


def test_no_strip_on_node_without_incoming_edge():
    graph = _make_graph(
        instances=[
            {"id": "start-1", "is_start_node": True, "parameters": [], "input_port_instances": []},
            {
                "id": "orphan-1",
                "name": "Orphan",
                "parameters": [],
                "input_port_instances": [{"name": "messages", "field_expression": {}}],
            },
        ],
        edges=[{"id": "e1", "origin": "start-1", "destination": "somewhere-else"}],
    )

    warnings = _strip_readonly_messages_overrides(graph)

    assert len(graph["component_instances"][1]["input_port_instances"]) == 1
    assert warnings == []


def test_no_op_when_no_edges():
    graph = _make_graph(instances=[{"id": "a", "parameters": [], "input_port_instances": []}], edges=[])
    warnings = _strip_readonly_messages_overrides(graph)
    assert warnings == []


def test_no_op_on_empty_graph():
    assert _strip_readonly_messages_overrides({}) == []
    assert _strip_readonly_messages_overrides({"component_instances": [], "edges": []}) == []
