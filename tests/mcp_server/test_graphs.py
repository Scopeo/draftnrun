from uuid import UUID

from mcp_server.tools.graphs import _assign_missing_ids, _warn_unknown_graph_keys


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
