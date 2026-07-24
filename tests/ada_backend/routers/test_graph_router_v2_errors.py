from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from ada_backend.routers.graph_router_v2 import test_api_call_output_ports_v2 as call_test_api_call_output_ports_v2
from ada_backend.schemas.pipeline.graph_schema import ApiCallOutputPortTestRequest
from ada_backend.services.errors import GraphNotBoundToProjectError


def _make_fake_user():
    user = MagicMock()
    user.id = uuid4()
    return user


def test_api_call_output_ports_validates_runner_project_binding_before_node_lookup():
    project_id = uuid4()
    graph_runner_id = uuid4()
    instance_id = uuid4()
    error = GraphNotBoundToProjectError(graph_runner_id, bound_project_id=uuid4(), expected_project_id=project_id)

    with (
        patch("ada_backend.routers.graph_router_v2.validate_graph_runner_belongs_to_project", side_effect=error),
        patch("ada_backend.routers.graph_router_v2.get_component_nodes") as mock_get_component_nodes,
        patch(
            "ada_backend.routers.graph_router_v2.test_and_persist_api_call_get_auto_output_ports"
        ) as mock_test_and_persist,
    ):
        with pytest.raises(GraphNotBoundToProjectError) as exc_info:
            call_test_api_call_output_ports_v2(
                project_id=project_id,
                graph_runner_id=graph_runner_id,
                instance_id=instance_id,
                payload=ApiCallOutputPortTestRequest(parameters=[]),
                user=_make_fake_user(),
                session=MagicMock(),
            )

    assert exc_info.value is error
    mock_get_component_nodes.assert_not_called()
    mock_test_and_persist.assert_not_called()


def test_api_call_output_ports_rejects_non_draft_graph_before_persistence():
    project_id = uuid4()
    graph_runner_id = uuid4()
    instance_id = uuid4()

    with (
        patch("ada_backend.routers.graph_router_v2.validate_graph_runner_belongs_to_project") as mock_validate_binding,
        patch(
            "ada_backend.routers.graph_router_v2.validate_graph_is_draft",
            side_effect=ValueError("Only draft versions can be updated"),
        ),
        patch("ada_backend.routers.graph_router_v2.get_component_nodes") as mock_get_component_nodes,
        patch(
            "ada_backend.routers.graph_router_v2.test_and_persist_api_call_get_auto_output_ports"
        ) as mock_test_and_persist,
    ):
        with pytest.raises(HTTPException) as exc_info:
            call_test_api_call_output_ports_v2(
                project_id=project_id,
                graph_runner_id=graph_runner_id,
                instance_id=instance_id,
                payload=ApiCallOutputPortTestRequest(parameters=[]),
                user=_make_fake_user(),
                session=MagicMock(),
            )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Only draft versions can be updated"
    mock_validate_binding.assert_called_once()
    mock_get_component_nodes.assert_not_called()
    mock_test_and_persist.assert_not_called()


def test_api_call_output_ports_records_history_and_notifies_after_success():
    project_id = uuid4()
    graph_runner_id = uuid4()
    instance_id = uuid4()
    session = MagicMock()
    node = MagicMock()
    node.id = instance_id

    with (
        patch("ada_backend.routers.graph_router_v2.validate_graph_runner_belongs_to_project") as mock_validate_binding,
        patch("ada_backend.routers.graph_router_v2.validate_graph_is_draft") as mock_validate_draft,
        patch("ada_backend.routers.graph_router_v2.get_component_nodes", return_value=[node]),
        patch(
            "ada_backend.routers.graph_router_v2.test_and_persist_api_call_get_auto_output_ports",
            return_value=["account_id", "status"],
        ) as mock_test_and_persist,
        patch("ada_backend.routers.graph_router_v2.graph_mutation_helpers.record_modification_history") as mock_record,
        patch("ada_backend.routers.graph_router_v2.notify_graph_changed") as mock_notify,
    ):
        response = call_test_api_call_output_ports_v2(
            project_id=project_id,
            graph_runner_id=graph_runner_id,
            instance_id=instance_id,
            payload=ApiCallOutputPortTestRequest(parameters=[]),
            user=_make_fake_user(),
            session=session,
        )

    assert response.output_port_names == ["account_id", "status"]
    mock_validate_binding.assert_called_once_with(session, graph_runner_id, project_id)
    mock_validate_draft.assert_called_once_with(session, graph_runner_id)
    mock_test_and_persist.assert_called_once_with(session=session, component_instance_id=instance_id, parameters=[])
    mock_record.assert_called_once()
    assert mock_record.call_args.args == (session, graph_runner_id)
    assert mock_record.call_args.kwargs["user_id"]
    mock_notify.assert_called_once_with(project_id, graph_runner_id, "component.updated")
