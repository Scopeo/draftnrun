from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from mcp_server.client import ToolError
from mcp_server.tools import graphs
from mcp_server.tools.graphs import _assign_missing_ids, _validate_component_instances, _warn_unknown_graph_keys
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
