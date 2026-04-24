from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from ada_backend.schemas.pipeline.graph_schema import (
    GraphMapEdgeSchema,
    GraphMapNodeRefSchema,
    GraphMapRelationshipSchema,
    GraphTopologyNodeSchema,
)
from ada_backend.services.errors import GraphValidationError
from ada_backend.services.graph.graph_topology_v2_service import sync_graph_topology


@pytest.fixture
def session():
    return MagicMock()


@pytest.fixture
def graph_runner_id():
    return uuid4()


class TestSyncGraphTopology:
    @patch("ada_backend.services.graph.graph_topology_v2_service.upsert_edge")
    @patch("ada_backend.services.graph.graph_topology_v2_service.get_edges")
    @patch("ada_backend.services.graph.graph_topology_v2_service.upsert_component_node")
    @patch("ada_backend.services.graph.graph_topology_v2_service.get_component_nodes")
    @patch("ada_backend.services.graph.graph_topology_v2_service.graph_runner_exists")
    def test_syncs_edges_and_nodes(
        self,
        mock_gr_exists,
        mock_get_nodes,
        mock_upsert_node,
        mock_get_edges,
        mock_upsert_edge,
        session,
        graph_runner_id,
    ):
        id_a = uuid4()
        id_b = uuid4()

        node_a = MagicMock()
        node_a.id = id_a
        node_b = MagicMock()
        node_b.id = id_b
        mock_get_nodes.return_value = [node_a, node_b]
        mock_get_edges.return_value = []
        mock_gr_exists.return_value = False

        nodes = [
            GraphTopologyNodeSchema(instance_id=id_a, label="Start", is_start_node=True),
            GraphTopologyNodeSchema(instance_id=id_b, label="Agent", is_start_node=False),
        ]
        edge_id = uuid4()
        edges = [
            GraphMapEdgeSchema(
                id=edge_id,
                **{"from": GraphMapNodeRefSchema(id=id_a), "to": GraphMapNodeRefSchema(id=id_b)},
            ),
        ]

        sync_graph_topology(session, graph_runner_id, nodes=nodes, edges=edges, relationships=[])

        assert mock_upsert_node.call_count == 2
        mock_upsert_edge.assert_called_once()

    @patch("ada_backend.services.graph.graph_topology_v2_service.get_component_nodes")
    def test_raises_on_missing_node(self, mock_get_nodes, session, graph_runner_id):
        mock_get_nodes.return_value = []

        nodes = [GraphTopologyNodeSchema(instance_id=uuid4(), label="Ghost")]

        with pytest.raises(GraphValidationError, match="do not exist in graph"):
            sync_graph_topology(session, graph_runner_id, nodes=nodes, edges=[], relationships=[])

    @patch("ada_backend.services.graph.graph_topology_v2_service.delete_edge")
    @patch("ada_backend.services.graph.graph_topology_v2_service.get_edges")
    @patch("ada_backend.services.graph.graph_topology_v2_service.upsert_component_node")
    @patch("ada_backend.services.graph.graph_topology_v2_service.get_component_nodes")
    def test_deletes_removed_edges(
        self, mock_get_nodes, mock_upsert_node, mock_get_edges, mock_del_edge, session, graph_runner_id
    ):
        id_a = uuid4()
        node_a = MagicMock()
        node_a.id = id_a
        mock_get_nodes.return_value = [node_a]

        old_edge = MagicMock()
        old_edge.id = uuid4()
        mock_get_edges.return_value = [old_edge]

        nodes = [GraphTopologyNodeSchema(instance_id=id_a, label="Start")]

        sync_graph_topology(session, graph_runner_id, nodes=nodes, edges=[], relationships=[])

        mock_del_edge.assert_called_once_with(session, old_edge.id)

    @patch("ada_backend.services.graph.graph_topology_v2_service.upsert_sub_component_input")
    @patch(
        "ada_backend.services.graph.graph_topology_v2_service.get_component_parameter_definition_by_component_version"
    )
    @patch("ada_backend.services.graph.graph_topology_v2_service.get_component_instance_by_id")
    @patch("ada_backend.services.graph.graph_topology_v2_service.get_edges")
    @patch("ada_backend.services.graph.graph_topology_v2_service.upsert_component_node")
    @patch("ada_backend.services.graph.graph_topology_v2_service.get_component_nodes")
    def test_syncs_relationships(
        self,
        mock_get_nodes,
        mock_upsert_node,
        mock_get_edges,
        mock_get_inst,
        mock_get_param_defs,
        mock_upsert_sub,
        session,
        graph_runner_id,
    ):
        parent_id = uuid4()
        child_id = uuid4()
        node_p = MagicMock()
        node_p.id = parent_id
        node_c = MagicMock()
        node_c.id = child_id
        mock_get_nodes.return_value = [node_p, node_c]
        mock_get_edges.return_value = []

        parent_inst = MagicMock()
        parent_inst.component_version_id = uuid4()
        mock_get_inst.return_value = parent_inst

        param_def = MagicMock()
        param_def.name = "tool"
        param_def.id = uuid4()
        mock_get_param_defs.return_value = [param_def]

        nodes = [
            GraphTopologyNodeSchema(instance_id=parent_id, label="Parent"),
            GraphTopologyNodeSchema(instance_id=child_id, label="Child"),
        ]
        relationships = [
            GraphMapRelationshipSchema(
                parent=GraphMapNodeRefSchema(id=parent_id),
                child=GraphMapNodeRefSchema(id=child_id),
                parameter_name="tool",
            ),
        ]

        sync_graph_topology(session, graph_runner_id, nodes=nodes, edges=[], relationships=relationships)

        mock_upsert_sub.assert_called_once()
