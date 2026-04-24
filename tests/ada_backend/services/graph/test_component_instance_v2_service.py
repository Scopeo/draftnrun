from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from ada_backend.schemas.pipeline.graph_schema import ComponentCreateV2Schema, ComponentUpdateV2Schema
from ada_backend.services.graph.component_instance_v2_service import (
    create_component_in_graph,
    delete_component_from_graph,
    update_single_component,
)


@pytest.fixture
def session():
    return MagicMock()


@pytest.fixture
def ids():
    return {
        "graph_runner_id": uuid4(),
        "project_id": uuid4(),
        "component_id": uuid4(),
        "component_version_id": uuid4(),
        "instance_id": uuid4(),
    }


class TestCreateComponentInGraph:
    @patch("ada_backend.services.graph.component_instance_v2_service.upsert_component_node")
    @patch("ada_backend.services.graph.component_instance_v2_service.create_or_update_component_instance")
    def test_creates_instance_and_node(self, mock_create, mock_upsert_node, session, ids):
        created_id = uuid4()
        mock_create.return_value = created_id

        payload = ComponentCreateV2Schema(
            component_id=ids["component_id"],
            component_version_id=ids["component_version_id"],
            label="My LLM",
            is_start_node=False,
            parameters=[{"name": "prompt", "value": "hello"}],
        )

        result = create_component_in_graph(session, ids["graph_runner_id"], ids["project_id"], payload)

        assert result == created_id
        mock_create.assert_called_once()
        instance_schema = mock_create.call_args[0][1]
        assert instance_schema.name == "My LLM"
        assert instance_schema.component_id == ids["component_id"]

        mock_upsert_node.assert_called_once_with(
            session,
            graph_runner_id=ids["graph_runner_id"],
            component_instance_id=created_id,
            is_start_node=False,
        )


class TestUpdateSingleComponent:
    @patch("ada_backend.services.graph.component_instance_v2_service.upsert_component_node")
    @patch("ada_backend.services.graph.component_instance_v2_service.create_or_update_component_instance")
    @patch("ada_backend.services.graph.component_instance_v2_service.get_component_nodes")
    @patch("ada_backend.services.graph.component_instance_v2_service.get_component_instance_by_id")
    def test_updates_existing_instance(
        self, mock_get_inst, mock_get_nodes, mock_create, mock_upsert_node, session, ids
    ):
        mock_instance = MagicMock()
        mock_instance.name = "Old Name"
        mock_instance.component_version_id = ids["component_version_id"]
        mock_instance.component_version.component_id = ids["component_id"]
        mock_get_inst.return_value = mock_instance

        node = MagicMock()
        node.id = ids["instance_id"]
        node.is_start_node = False
        mock_get_nodes.return_value = [node]

        payload = ComponentUpdateV2Schema(
            parameters=[{"name": "prompt", "value": "updated"}],
            label="New Name",
        )

        update_single_component(session, ids["graph_runner_id"], ids["project_id"], ids["instance_id"], payload)

        mock_create.assert_called_once()
        instance_schema = mock_create.call_args[0][1]
        assert instance_schema.id == ids["instance_id"]
        assert instance_schema.name == "New Name"

    @patch("ada_backend.services.graph.component_instance_v2_service.get_component_nodes")
    @patch("ada_backend.services.graph.component_instance_v2_service.get_component_instance_by_id")
    def test_raises_if_not_in_graph(self, mock_get_inst, mock_get_nodes, session, ids):
        mock_get_inst.return_value = MagicMock()
        mock_get_nodes.return_value = []

        payload = ComponentUpdateV2Schema(parameters=[])
        with pytest.raises(ValueError, match="does not belong to graph"):
            update_single_component(session, ids["graph_runner_id"], ids["project_id"], ids["instance_id"], payload)

    @patch("ada_backend.services.graph.component_instance_v2_service.get_component_nodes")
    @patch("ada_backend.services.graph.component_instance_v2_service.get_component_instance_by_id")
    def test_raises_if_instance_not_found(self, mock_get_inst, mock_get_nodes, session, ids):
        mock_get_inst.return_value = None

        payload = ComponentUpdateV2Schema(parameters=[])
        with pytest.raises(ValueError, match="not found"):
            update_single_component(session, ids["graph_runner_id"], ids["project_id"], ids["instance_id"], payload)


class TestDeleteComponentFromGraph:
    @patch("ada_backend.services.graph.component_instance_v2_service.delete_node")
    @patch("ada_backend.services.graph.component_instance_v2_service.delete_component_instances_from_nodes")
    @patch("ada_backend.services.graph.component_instance_v2_service.get_edges")
    @patch("ada_backend.services.graph.component_instance_v2_service.get_component_nodes")
    def test_deletes_instance_and_cascades(
        self, mock_get_nodes, mock_get_edges, mock_del_inst, mock_del_node, session, ids
    ):
        node = MagicMock()
        node.id = ids["instance_id"]
        mock_get_nodes.return_value = [node]
        mock_get_edges.return_value = []
        session.query.return_value.filter.return_value.all.return_value = []

        delete_component_from_graph(session, ids["graph_runner_id"], ids["instance_id"])

        mock_del_inst.assert_called_once_with(session, {ids["instance_id"]})
        mock_del_node.assert_called_once_with(session, ids["instance_id"])

    @patch("ada_backend.services.graph.component_instance_v2_service.get_component_nodes")
    def test_raises_if_not_in_graph(self, mock_get_nodes, session, ids):
        mock_get_nodes.return_value = []

        with pytest.raises(ValueError, match="does not belong to graph"):
            delete_component_from_graph(session, ids["graph_runner_id"], ids["instance_id"])

    @patch("ada_backend.services.graph.component_instance_v2_service.delete_node")
    @patch("ada_backend.services.graph.component_instance_v2_service.delete_component_instances_from_nodes")
    @patch("ada_backend.services.graph.component_instance_v2_service.delete_edge")
    @patch("ada_backend.services.graph.component_instance_v2_service.get_edges")
    @patch("ada_backend.services.graph.component_instance_v2_service.get_component_nodes")
    def test_cascades_edge_deletion(
        self, mock_get_nodes, mock_get_edges, mock_del_edge, mock_del_inst, mock_del_node, session, ids
    ):
        node = MagicMock()
        node.id = ids["instance_id"]
        mock_get_nodes.return_value = [node]

        edge = MagicMock()
        edge.id = uuid4()
        edge.source_node_id = ids["instance_id"]
        edge.target_node_id = uuid4()
        mock_get_edges.return_value = [edge]
        session.query.return_value.filter.return_value.all.return_value = []

        delete_component_from_graph(session, ids["graph_runner_id"], ids["instance_id"])

        mock_del_edge.assert_called_once_with(session, edge.id)
