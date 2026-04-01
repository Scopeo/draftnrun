import uuid
from types import SimpleNamespace

import httpx
import openai

from ada_backend.services.graph_reachability import find_reachable_nodes
from engine.components.errors import LLMProviderError
from engine.llm_services.providers.base_provider import BaseProvider


def _node(node_id: str, *, is_trigger: bool = False, name: str = ""):
    return SimpleNamespace(
        id=uuid.UUID(node_id),
        name=name or f"node-{node_id[:8]}",
        is_trigger=is_trigger,
    )


def _edge(source_id: str | None, target_id: str):
    return SimpleNamespace(
        source_node_id=uuid.UUID(source_id) if source_id else None,
        target_node_id=uuid.UUID(target_id),
    )


ID_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
ID_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
ID_C = "cccccccc-cccc-cccc-cccc-cccccccccccc"
ID_D = "dddddddd-dddd-dddd-dddd-dddddddddddd"
ID_E = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"


class TestFindReachableNodes:
    """Unit tests for find_reachable_nodes."""

    def test_linear_chain_all_reachable(self):
        """trigger -> B -> C  ⇒ all reachable."""
        nodes = [_node(ID_A), _node(ID_B), _node(ID_C)]
        edges = [_edge(ID_A, ID_B), _edge(ID_B, ID_C)]
        result = find_reachable_nodes(nodes, edges, {ID_A})
        assert result == {ID_A, ID_B, ID_C}

    def test_disconnected_node_excluded(self):
        """trigger -> B, C is disconnected  ⇒ C not reachable."""
        nodes = [_node(ID_A), _node(ID_B), _node(ID_C)]
        edges = [_edge(ID_A, ID_B)]
        result = find_reachable_nodes(nodes, edges, {ID_A})
        assert result == {ID_A, ID_B}
        assert ID_C not in result

    def test_no_trigger_nodes_returns_empty(self):
        """No trigger nodes → empty set, nothing executes."""
        nodes = [_node(ID_A), _node(ID_B)]
        edges = [_edge(ID_A, ID_B)]
        result = find_reachable_nodes(nodes, edges, set())
        assert result == set()

    def test_multiple_trigger_nodes(self):
        """Two triggers, each with their own subtree → union of both."""
        nodes = [_node(ID_A), _node(ID_B), _node(ID_C), _node(ID_D)]
        edges = [_edge(ID_A, ID_B), _edge(ID_C, ID_D)]
        result = find_reachable_nodes(nodes, edges, {ID_A, ID_C})
        assert result == {ID_A, ID_B, ID_C, ID_D}

    def test_diamond_graph(self):
        """trigger -> B, trigger -> C, B -> D, C -> D  ⇒ all reachable."""
        nodes = [_node(ID_A), _node(ID_B), _node(ID_C), _node(ID_D)]
        edges = [
            _edge(ID_A, ID_B),
            _edge(ID_A, ID_C),
            _edge(ID_B, ID_D),
            _edge(ID_C, ID_D),
        ]
        result = find_reachable_nodes(nodes, edges, {ID_A})
        assert result == {ID_A, ID_B, ID_C, ID_D}

    def test_edge_with_null_source_ignored(self):
        """Edges with source_node_id=None should be skipped."""
        nodes = [_node(ID_A), _node(ID_B)]
        edges = [_edge(None, ID_B)]
        result = find_reachable_nodes(nodes, edges, {ID_A})
        assert result == {ID_A}
        assert ID_B not in result

    def test_trigger_node_not_in_graph_is_skipped(self):
        """If a trigger_node_id doesn't exist in the node list, skip gracefully."""
        nodes = [_node(ID_A)]
        edges = []
        missing_trigger = "ffffffff-ffff-ffff-ffff-ffffffffffff"
        result = find_reachable_nodes(nodes, edges, {missing_trigger})
        assert result == set()

    def test_single_trigger_no_edges(self):
        """A trigger with no outgoing edges → only itself is reachable."""
        nodes = [_node(ID_A), _node(ID_B)]
        edges = []
        result = find_reachable_nodes(nodes, edges, {ID_A})
        assert result == {ID_A}

    def test_mixed_reachable_and_unreachable(self):
        """
        trigger(A) -> B -> C, D -> E (disconnected cluster)
        ⇒ {A, B, C} reachable, {D, E} not.
        """
        nodes = [
            _node(ID_A),
            _node(ID_B),
            _node(ID_C),
            _node(ID_D),
            _node(ID_E),
        ]
        edges = [
            _edge(ID_A, ID_B),
            _edge(ID_B, ID_C),
            _edge(ID_D, ID_E),
        ]
        result = find_reachable_nodes(nodes, edges, {ID_A})
        assert result == {ID_A, ID_B, ID_C}
        assert ID_D not in result
        assert ID_E not in result


class TestIsTriggerFiltering:
    """Tests verifying that is_trigger drives which nodes are treated as triggers."""

    def test_only_trigger_flagged_nodes_used_as_roots(self):
        """
        A(is_trigger=True) -> B, C(is_trigger=False, disconnected)
        ⇒ C should NOT be reachable.
        """
        nodes = [
            _node(ID_A, is_trigger=True, name="Start"),
            _node(ID_B, is_trigger=False, name="AI Agent"),
            _node(ID_C, is_trigger=False, name="Linkup"),
        ]
        edges = [_edge(ID_A, ID_B)]

        trigger_ids = {str(n.id) for n in nodes if n.is_trigger}
        reachable = find_reachable_nodes(nodes, edges, trigger_ids)

        assert reachable == {ID_A, ID_B}
        assert ID_C not in reachable

    def test_non_trigger_node_not_treated_as_start(self):
        """
        A(is_trigger=False) -> B: even though A has an edge, if it's not a
        trigger the graph has no entry points → nothing reachable.
        """
        nodes = [
            _node(ID_A, is_trigger=False, name="RegularBlock"),
            _node(ID_B, is_trigger=False, name="AI Agent"),
        ]
        edges = [_edge(ID_A, ID_B)]

        trigger_ids = {str(n.id) for n in nodes if n.is_trigger}
        reachable = find_reachable_nodes(nodes, edges, trigger_ids)

        assert reachable == set()

    def test_unreachable_nodes_identified_correctly(self):
        """
        trigger(A) -> B, C is disconnected
        ⇒ unreachable = {C}, warning names = ["Linkup"].
        """
        nodes = [
            _node(ID_A, is_trigger=True, name="Start"),
            _node(ID_B, is_trigger=False, name="AI Agent"),
            _node(ID_C, is_trigger=False, name="Linkup"),
        ]
        edges = [_edge(ID_A, ID_B)]

        trigger_ids = {str(n.id) for n in nodes if n.is_trigger}
        reachable = find_reachable_nodes(nodes, edges, trigger_ids)
        all_ids = {str(n.id) for n in nodes}
        unreachable = all_ids - reachable

        unreachable_names = [n.name for n in nodes if str(n.id) in unreachable]
        assert unreachable_names == ["Linkup"]

    def test_two_triggers_with_shared_downstream(self):
        """
        A(trigger) -> C, B(trigger) -> C, D disconnected
        ⇒ {A, B, C} reachable, D not.
        """
        nodes = [
            _node(ID_A, is_trigger=True, name="Start1"),
            _node(ID_B, is_trigger=True, name="Start2"),
            _node(ID_C, is_trigger=False, name="Agent"),
            _node(ID_D, is_trigger=False, name="Orphan"),
        ]
        edges = [_edge(ID_A, ID_C), _edge(ID_B, ID_C)]

        trigger_ids = {str(n.id) for n in nodes if n.is_trigger}
        reachable = find_reachable_nodes(nodes, edges, trigger_ids)

        assert reachable == {ID_A, ID_B, ID_C}
        assert ID_D not in reachable


class TestExtractProviderMessage:
    """Regression tests for LLM provider error extraction (DRA-1181)."""

    def _make_httpx_response(self, status_code: int = 400) -> httpx.Response:
        resp = httpx.Response(status_code=status_code, request=httpx.Request("POST", "https://api.example.com"))
        return resp

    def test_openai_bad_request_with_body_dict(self):
        resp = self._make_httpx_response(400)
        exc = openai.BadRequestError(
            message="Error code: 400",
            response=resp,
            body={"message": "Invalid model: mistral-medium-c21211-r0-75", "type": "invalid_model"},
        )
        msg, status = BaseProvider.extract_error_message(exc)
        assert msg == "Invalid model: mistral-medium-c21211-r0-75"
        assert status == 400

    def test_openai_auth_error(self):
        resp = self._make_httpx_response(401)
        exc = openai.AuthenticationError(
            message="Error code: 401",
            response=resp,
            body={"message": "Invalid API key", "type": "auth_error"},
        )
        msg, status = BaseProvider.extract_error_message(exc)
        assert msg == "Invalid API key"
        assert status == 401

    def test_openai_api_status_error_with_string_body(self):
        resp = self._make_httpx_response(500)
        exc = openai.InternalServerError(
            message="Error code: 500",
            response=resp,
            body="Internal server error",
        )
        msg, status = BaseProvider.extract_error_message(exc)
        assert msg == "Internal server error"
        assert status == 500

    def test_openai_api_connection_error(self):
        exc = openai.APIConnectionError(request=httpx.Request("POST", "https://api.example.com"))
        msg, status = BaseProvider.extract_error_message(exc)
        assert "Connection error" in msg
        assert status is None

    def test_llm_provider_error_str_clean(self):
        err = LLMProviderError("Invalid model: foo-bar", status_code=400)
        assert str(err) == "LLM provider error (400): Invalid model: foo-bar"
        assert err.provider_message == "Invalid model: foo-bar"
        assert err.status_code == 400

    def test_llm_provider_error_str_no_status(self):
        err = LLMProviderError("Connection timed out")
        assert str(err) == "LLM provider error: Connection timed out"
        assert err.status_code is None
