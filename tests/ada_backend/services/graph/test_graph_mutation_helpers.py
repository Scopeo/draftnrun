from unittest.mock import MagicMock, patch
from uuid import uuid4

from ada_backend.schemas.pipeline.graph_schema import (
    ComponentCreateV2Schema,
    ComponentUpdateV2Schema,
    GraphTopologySaveV2Schema,
)
from ada_backend.services.graph.graph_mutation_helpers import (
    create_component_v2,
    delete_component_v2,
    save_graph_topology_v2,
    update_component_v2,
)

P = "ada_backend.services.graph.graph_mutation_helpers"


def _mock_history():
    h = MagicMock()
    h.created_at = None
    h.user_id = None
    return h


class TestGraphMutationPublishesEvents:
    def test_create_component_publishes_graph_changed(self):
        session = MagicMock()
        graph_runner_id = uuid4()
        project_id = uuid4()
        user_id = uuid4()
        payload = MagicMock(spec=ComponentCreateV2Schema)
        payload.label = "test"
        payload.is_start_node = False

        with (
            patch(f"{P}.validate_graph_is_draft"),
            patch(f"{P}.create_component_in_graph", return_value=uuid4()),
            patch(f"{P}.record_modification_history", return_value=_mock_history()),
            patch(f"{P}.publish_graph_update_event") as mock_pub,
        ):
            create_component_v2(session, graph_runner_id, project_id, user_id, payload)

            mock_pub.assert_called_once()
            event = mock_pub.call_args.args[1]
            assert event["type"] == "graph.changed"
            assert event["action"] == "component.created"
            assert event["graph_runner_id"] == str(graph_runner_id)

    def test_update_component_publishes_graph_changed(self):
        session = MagicMock()
        graph_runner_id = uuid4()
        project_id = uuid4()
        instance_id = uuid4()
        user_id = uuid4()
        payload = MagicMock(spec=ComponentUpdateV2Schema)
        payload.label = "test"
        payload.is_start_node = False

        with (
            patch(f"{P}.validate_graph_is_draft"),
            patch(f"{P}.update_single_component"),
            patch(f"{P}.record_modification_history", return_value=_mock_history()),
            patch(f"{P}.publish_graph_update_event") as mock_pub,
            patch(f"{P}.get_component_nodes", return_value=[]),
        ):
            update_component_v2(session, graph_runner_id, project_id, instance_id, user_id, payload)

            mock_pub.assert_called_once()
            event = mock_pub.call_args.args[1]
            assert event["type"] == "graph.changed"
            assert event["action"] == "component.updated"

    def test_delete_component_publishes_graph_changed(self):
        session = MagicMock()
        graph_runner_id = uuid4()
        project_id = uuid4()
        instance_id = uuid4()
        user_id = uuid4()

        with (
            patch(f"{P}.validate_graph_is_draft"),
            patch(f"{P}.delete_component_from_graph"),
            patch(f"{P}.record_modification_history", return_value=_mock_history()),
            patch(f"{P}.publish_graph_update_event") as mock_pub,
        ):
            delete_component_v2(session, graph_runner_id, project_id, instance_id, user_id)

            mock_pub.assert_called_once()
            event = mock_pub.call_args.args[1]
            assert event["type"] == "graph.changed"
            assert event["action"] == "component.deleted"

    def test_save_topology_publishes_graph_changed(self):
        session = MagicMock()
        graph_runner_id = uuid4()
        project_id = uuid4()
        user_id = uuid4()
        payload = MagicMock(spec=GraphTopologySaveV2Schema)
        payload.last_edited_time = None
        payload.nodes = []
        payload.edges = []
        payload.relationships = []

        with (
            patch(f"{P}.validate_graph_is_draft"),
            patch(f"{P}.check_optimistic_lock"),
            patch(f"{P}.sync_graph_topology"),
            patch(f"{P}.record_modification_history", return_value=_mock_history()),
            patch(f"{P}.publish_graph_update_event") as mock_pub,
        ):
            save_graph_topology_v2(session, graph_runner_id, project_id, user_id, payload)

            mock_pub.assert_called_once()
            event = mock_pub.call_args.args[1]
            assert event["type"] == "graph.changed"
            assert event["action"] == "topology.updated"
