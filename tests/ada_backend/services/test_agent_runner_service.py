import uuid
from types import SimpleNamespace

from ada_backend.services.graph_reachability import find_reachable_nodes


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
