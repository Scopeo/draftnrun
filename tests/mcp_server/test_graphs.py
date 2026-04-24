from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from mcp_server.client import ToolError
from mcp_server.tools import graphs
from mcp_server.tools.graphs import (
    _assign_missing_ids,
    _convert_field_expressions_to_write_format,
    _validate_component_instances,
    _warn_unknown_graph_keys,
)
from tests.mcp_server.conftest import FAKE_PROJECT_ID, FAKE_RUNNER_ID


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


# --- _validate_component_instances ---


def test_validate_component_instances_raises_on_missing_version_id():
    graph_data = {
        "component_instances": [
            {"id": "abc", "name": "Start", "component_version_id": "v1"},
            {"id": "def", "name": "AI Agent"},
        ],
    }
    with pytest.raises(ToolError, match="AI Agent.*missing.*component_version_id"):
        _validate_component_instances(graph_data)


def test_validate_component_instances_passes_with_valid_data():
    graph_data = {
        "component_instances": [
            {"id": "abc", "name": "Start", "component_version_id": "v1"},
            {"id": "def", "name": "AI Agent", "component_version_id": "v2"},
        ],
    }
    _validate_component_instances(graph_data)


# --- _warn_unknown_graph_keys ---


def test_warns_on_typo_key():
    graph_data = {
        "component_instances": [],
        "edges": [],
        "ports_mappings": [],  # typo
    }
    warnings = _warn_unknown_graph_keys(graph_data)
    assert len(warnings) == 1
    assert "ports_mappings" in warnings[0]


def test_no_warning_on_valid_keys():
    graph_data = {
        "component_instances": [],
        "edges": [],
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


# --- publish_to_production (custom tool → POST .../deploy) ---


@pytest.mark.asyncio
async def test_publish_to_production_calls_deploy_endpoint(monkeypatch, fake_mcp):
    deploy_response = {
        "project_id": FAKE_PROJECT_ID,
        "draft_graph_runner_id": "00000000-0000-4000-8000-aaaaaaaaaaaa",
        "prod_graph_runner_id": FAKE_RUNNER_ID,
        "previous_prod_graph_runner_id": None,
    }
    post_mock = AsyncMock(return_value=deploy_response)

    monkeypatch.setattr(graphs, "_get_auth", lambda: ("jwt-token", "user-123"))
    monkeypatch.setattr(graphs.api, "post", post_mock)

    graphs.register(fake_mcp)
    result = await fake_mcp.tools["publish_to_production"](FAKE_PROJECT_ID, FAKE_RUNNER_ID)

    assert result == deploy_response
    post_mock.assert_awaited_once_with(
        f"/projects/{FAKE_PROJECT_ID}/graph/{FAKE_RUNNER_ID}/deploy", "jwt-token"
    )


# --- get_draft_graph (convenience → resolves draft runner automatically) ---


@pytest.mark.asyncio
async def test_get_draft_graph_resolves_draft_runner(monkeypatch, fake_mcp):
    project_response = {
        "graph_runners": [
            {"id": FAKE_RUNNER_ID, "env": "draft", "tag_name": None},
            {"id": "00000000-0000-4000-8000-bbbbbbbbbbbb", "env": "production", "tag_name": "v1"},
        ],
    }
    graph_response = {"component_instances": [], "edges": []}

    call_log = []

    async def mock_get(path, token, *, trim=True, **params):
        call_log.append((path, trim))
        if "/graph/" in path:
            return graph_response
        return project_response

    monkeypatch.setattr(graphs, "_get_auth", lambda: ("jwt-token", "user-123"))
    monkeypatch.setattr(graphs.api, "get", mock_get)

    graphs.register(fake_mcp)
    result = await fake_mcp.tools["get_draft_graph"](FAKE_PROJECT_ID)

    assert result["graph_runner_id"] == FAKE_RUNNER_ID
    assert result["graph"] == graph_response
    assert call_log[0] == (f"/projects/{FAKE_PROJECT_ID}", True)
    assert call_log[1] == (f"/projects/{FAKE_PROJECT_ID}/graph/{FAKE_RUNNER_ID}", False)


@pytest.mark.asyncio
async def test_get_draft_graph_raises_when_no_draft(monkeypatch, fake_mcp):
    project_response = {
        "graph_runners": [
            {"id": "00000000-0000-4000-8000-bbbbbbbbbbbb", "env": "production", "tag_name": "v1"},
        ],
    }

    monkeypatch.setattr(graphs, "_get_auth", lambda: ("jwt-token", "user-123"))
    monkeypatch.setattr(graphs.api, "get", AsyncMock(return_value=project_response))

    graphs.register(fake_mcp)
    with pytest.raises(ToolError, match="No editable draft runner found"):
        await fake_mcp.tools["get_draft_graph"](FAKE_PROJECT_ID)


@pytest.mark.asyncio
async def test_get_draft_graph_skips_tagged_drafts(monkeypatch, fake_mcp):
    """A draft runner with a tag_name is a snapshot, not the editable draft."""
    project_response = {
        "graph_runners": [
            {"id": "00000000-0000-4000-8000-cccccccccccc", "env": "draft", "tag_name": "v2-snapshot"},
            {"id": FAKE_RUNNER_ID, "env": "draft", "tag_name": None},
        ],
    }
    graph_response = {"component_instances": [{"id": "node-1"}], "edges": []}

    async def mock_get(path, token, *, trim=True, **params):
        if "/graph/" in path:
            return graph_response
        return project_response

    monkeypatch.setattr(graphs, "_get_auth", lambda: ("jwt-token", "user-123"))
    monkeypatch.setattr(graphs.api, "get", mock_get)

    graphs.register(fake_mcp)
    result = await fake_mcp.tools["get_draft_graph"](FAKE_PROJECT_ID)

    assert result["graph_runner_id"] == FAKE_RUNNER_ID


# --- promote_version_to_env (factory proxy → PUT .../env/{env}) ---


def test_promote_version_to_env_registered(fake_mcp):
    graphs.register(fake_mcp)
    assert "promote_version_to_env" in fake_mcp.tools
    assert "get_graph_v2" in fake_mcp.tools
    assert "create_component_v2" in fake_mcp.tools
    assert "update_component_v2" in fake_mcp.tools
    assert "delete_component_v2" in fake_mcp.tools
    assert "update_graph_topology_v2" in fake_mcp.tools


# --- _convert_field_expressions_to_write_format ---


def test_convert_field_expressions_moves_to_input_port_instances():
    json_build_expr = {
        "type": "json_build",
        "template": {"Authorization": "Bearer __REF_0__"},
        "refs": {"__REF_0__": {"type": "var", "name": "hubspot_token"}},
    }
    instances = [
        {
            "id": "inst-1",
            "parameters": [],
            "field_expressions": [
                {"field_name": "headers", "expression_json": json_build_expr},
            ],
            "input_port_instances": [],
        }
    ]

    _convert_field_expressions_to_write_format(instances)

    assert "field_expressions" not in instances[0]
    ipis = instances[0]["input_port_instances"]
    assert len(ipis) == 1
    assert ipis[0]["name"] == "headers"
    assert ipis[0]["field_expression"]["expression_json"] == json_build_expr


def test_convert_field_expressions_skips_when_ipi_already_exists():
    expr_json = {"type": "literal", "value": "hello"}
    instances = [
        {
            "id": "inst-1",
            "field_expressions": [
                {"field_name": "headers", "expression_json": expr_json},
            ],
            "input_port_instances": [
                {"name": "headers", "field_expression": {"expression_json": {"type": "literal", "value": "existing"}}},
            ],
        }
    ]

    _convert_field_expressions_to_write_format(instances)

    assert len(instances[0]["input_port_instances"]) == 1
    assert instances[0]["input_port_instances"][0]["field_expression"]["expression_json"]["value"] == "existing"


def test_convert_field_expressions_no_op_when_empty():
    instances = [{"id": "inst-1", "parameters": []}]
    _convert_field_expressions_to_write_format(instances)
    assert "input_port_instances" not in instances[0]


def test_convert_field_expressions_handles_multiple_expressions():
    instances = [
        {
            "id": "inst-1",
            "field_expressions": [
                {"field_name": "headers", "expression_json": {"type": "var", "name": "token"}},
                {"field_name": "body", "expression_json": {"type": "literal", "value": "test"}},
            ],
        }
    ]

    _convert_field_expressions_to_write_format(instances)

    ipis = instances[0]["input_port_instances"]
    assert len(ipis) == 2
    names = {ipi["name"] for ipi in ipis}
    assert names == {"headers", "body"}


# --- update_component_parameters field expression round-trip ---


FAKE_INSTANCE_ID = "00000000-0000-4000-8000-111111111111"


@pytest.mark.asyncio
async def test_update_component_parameters_preserves_json_build_expressions(monkeypatch, fake_mcp):
    """Regression: update_component_parameters must convert field_expressions
    to input_port_instances so complex expressions (json_build) survive the
    read-modify-write round-trip (DRA-1191)."""
    json_build_expr = {
        "type": "json_build",
        "template": {"Authorization": "Bearer __REF_0__"},
        "refs": {"__REF_0__": {"type": "var", "name": "hubspot_token"}},
    }

    graph_response = {
        "component_instances": [
            {
                "id": FAKE_INSTANCE_ID,
                "name": "Get hubspot contact",
                "parameters": [
                    {"name": "headers", "value": "[JSON_BUILD]", "kind": "input"},
                    {"name": "initial_prompt", "value": "Hello", "kind": "textarea"},
                ],
                "field_expressions": [
                    {"field_name": "headers", "expression_json": json_build_expr},
                ],
                "input_port_instances": [],
            }
        ],
        "edges": [],
        "port_mappings": [],
        "relationships": [],
    }

    put_payload = {}
    put_path = None

    async def mock_get(path, token, *, trim=True, **params):
        return graph_response

    async def mock_put(path, token, *, json=None, **kwargs):
        nonlocal put_path
        put_path = path
        put_payload.update(json)
        return {"status": "ok"}

    monkeypatch.setattr(graphs, "_get_auth", lambda: ("jwt-token", "user-123"))
    monkeypatch.setattr(graphs.api, "get", mock_get)
    monkeypatch.setattr(graphs.api, "put", mock_put)

    graphs.register(fake_mcp)
    await fake_mcp.tools["update_component_parameters"](
        UUID(FAKE_PROJECT_ID),
        UUID(FAKE_RUNNER_ID),
        UUID(FAKE_INSTANCE_ID),
        {"initial_prompt": "Updated prompt"},
    )

    assert "/v2/" in put_path
    assert f"/components/{FAKE_INSTANCE_ID}" in put_path

    assert "component_instances" not in put_payload
    ipis = put_payload["input_port_instances"]
    headers_ipi = next(ipi for ipi in ipis if ipi["name"] == "headers")
    assert headers_ipi["field_expression"]["expression_json"] == json_build_expr

    sent_params = put_payload["parameters"]
    param_kinds = {p.get("kind", "parameter") for p in sent_params}
    assert "input" not in param_kinds

    updated_param = next(p for p in sent_params if p["name"] == "initial_prompt")
    assert updated_param["value"] == "Updated prompt"


@pytest.mark.asyncio
async def test_update_component_parameters_updates_input_kind_field_expressions(monkeypatch, fake_mcp):
    """Regression: updating a parameter with kind='input' must update the
    corresponding field_expression so the new value reaches the backend
    via input_port_instances."""
    graph_response = {
        "component_instances": [
            {
                "id": FAKE_INSTANCE_ID,
                "name": "Scorer",
                "parameters": [
                    {"name": "input", "value": "@{{start.messages}}", "kind": "input"},
                    {"name": "criteria", "value": "sentence is correct", "kind": "input"},
                    {"name": "additional_context", "value": None, "kind": "input"},
                    {"name": "completion_model", "value": "anthropic:claude-haiku-4-5", "kind": "parameter"},
                ],
                "field_expressions": [
                    {
                        "field_name": "input",
                        "expression_json": {"type": "ref", "instance": "start-id", "port": "messages"},
                        "expression_text": "@{{start-id.messages}}",
                    },
                    {
                        "field_name": "criteria",
                        "expression_json": {"type": "literal", "value": "sentence is correct"},
                        "expression_text": "sentence is correct",
                    },
                ],
                "input_port_instances": [],
            }
        ],
        "edges": [],
        "relationships": [],
    }

    put_payload = {}

    async def mock_get(path, token, *, trim=True, **params):
        return graph_response

    async def mock_put(path, token, *, json=None, **kwargs):
        put_payload.update(json)
        return {"status": "ok"}

    monkeypatch.setattr(graphs, "_get_auth", lambda: ("jwt-token", "user-123"))
    monkeypatch.setattr(graphs.api, "get", mock_get)
    monkeypatch.setattr(graphs.api, "put", mock_put)

    graphs.register(fake_mcp)
    result = await fake_mcp.tools["update_component_parameters"](
        UUID(FAKE_PROJECT_ID),
        UUID(FAKE_RUNNER_ID),
        UUID(FAKE_INSTANCE_ID),
        {"criteria": "Hello DIana", "additional_context": "Hi it is me"},
    )

    assert result["status"] == "ok"
    assert sorted(result["updated_parameters"]) == ["additional_context", "criteria"]

    ipis = put_payload["input_port_instances"]
    criteria_ipi = next(ipi for ipi in ipis if ipi["name"] == "criteria")
    assert criteria_ipi["field_expression"]["expression_json"] == {"type": "literal", "value": "Hello DIana"}

    context_ipi = next(ipi for ipi in ipis if ipi["name"] == "additional_context")
    assert context_ipi["field_expression"]["expression_json"] == {"type": "literal", "value": "Hi it is me"}

    input_ipi = next(ipi for ipi in ipis if ipi["name"] == "input")
    assert input_ipi["field_expression"]["expression_json"]["type"] == "ref"

    param_kinds = {p.get("kind", "parameter") for p in put_payload["parameters"]}
    assert "input" not in param_kinds


@pytest.mark.asyncio
async def test_update_component_parameters_removes_field_expression_on_null(monkeypatch, fake_mcp):
    """Setting a kind='input' parameter to None should remove its field_expression."""
    graph_response = {
        "component_instances": [
            {
                "id": FAKE_INSTANCE_ID,
                "name": "Scorer",
                "parameters": [
                    {"name": "criteria", "value": "old value", "kind": "input"},
                    {"name": "completion_model", "value": "model-x", "kind": "parameter"},
                ],
                "field_expressions": [
                    {
                        "field_name": "criteria",
                        "expression_json": {"type": "literal", "value": "old value"},
                        "expression_text": "old value",
                    },
                ],
                "input_port_instances": [],
            }
        ],
        "edges": [],
        "relationships": [],
    }

    put_payload = {}

    async def mock_get(path, token, *, trim=True, **params):
        return graph_response

    async def mock_put(path, token, *, json=None, **kwargs):
        put_payload.update(json)
        return {"status": "ok"}

    monkeypatch.setattr(graphs, "_get_auth", lambda: ("jwt-token", "user-123"))
    monkeypatch.setattr(graphs.api, "get", mock_get)
    monkeypatch.setattr(graphs.api, "put", mock_put)

    graphs.register(fake_mcp)
    await fake_mcp.tools["update_component_parameters"](
        UUID(FAKE_PROJECT_ID),
        UUID(FAKE_RUNNER_ID),
        UUID(FAKE_INSTANCE_ID),
        {"criteria": None},
    )

    ipis = put_payload["input_port_instances"]
    criteria_ipis = [ipi for ipi in ipis if ipi["name"] == "criteria"]
    assert len(criteria_ipis) == 0
