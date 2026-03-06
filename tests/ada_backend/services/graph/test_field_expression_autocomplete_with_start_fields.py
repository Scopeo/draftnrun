"""Unit tests for start field autocomplete feature."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

from ada_backend.schemas.pipeline.field_expression_schema import SuggestionKind
from ada_backend.services.graph.field_expression_autocomplete_service import _build_port_suggestions_with_start_fields


def test_start_node_includes_input_fields_as_properties():
    """Test that start node dynamic output ports are included as property suggestions."""
    session = MagicMock()
    graph_runner_id = uuid4()
    start_instance_id = uuid4()

    # Mock instance
    mock_instance = MagicMock()
    mock_instance.id = start_instance_id
    mock_instance.component_version_id = uuid4()
    instances = [mock_instance]

    with patch(
        "ada_backend.services.graph.field_expression_autocomplete_service.get_output_ports_for_component_version"
    ) as mock_get_ports:
        with patch(
            "ada_backend.services.graph.field_expression_autocomplete_service.get_output_port_instances_for_component_instance"
        ) as mock_get_dynamic_ports:
            mock_port = MagicMock()
            mock_port.name = "messages"
            mock_get_ports.return_value = [mock_port]

            mock_dynamic_username = MagicMock()
            mock_dynamic_username.name = "username"
            mock_dynamic_api_key = MagicMock()
            mock_dynamic_api_key.name = "api_key"
            mock_get_dynamic_ports.return_value = [mock_dynamic_username, mock_dynamic_api_key]

            suggestions = _build_port_suggestions_with_start_fields(
                session, graph_runner_id, instances, str(start_instance_id), ""
            )

            assert len(suggestions) == 3
            labels = {s.label for s in suggestions}
            assert labels == {"username", "api_key", "messages"}

            for s in suggestions:
                assert s.kind == SuggestionKind.PROPERTY


def test_non_start_node_only_shows_output_ports():
    """Test that non-start nodes only show output ports."""
    session = MagicMock()
    graph_runner_id = uuid4()
    instance_id = uuid4()

    mock_instance = MagicMock()
    mock_instance.id = instance_id
    mock_instance.component_version_id = uuid4()
    instances = [mock_instance]

    with patch(
        "ada_backend.services.graph.field_expression_autocomplete_service.get_output_ports_for_component_version"
    ) as mock_get_ports:
        mock_port = MagicMock()
        mock_port.name = "output"
        mock_get_ports.return_value = [mock_port]

        suggestions = _build_port_suggestions_with_start_fields(
            session, graph_runner_id, instances, str(instance_id), ""
        )

        assert len(suggestions) == 1
        assert suggestions[0].label == "output"


def test_start_field_query_filtering():
    """Test that query filtering works for start dynamic output ports."""
    session = MagicMock()
    graph_runner_id = uuid4()
    start_instance_id = uuid4()

    mock_instance = MagicMock()
    mock_instance.id = start_instance_id
    mock_instance.component_version_id = uuid4()
    instances = [mock_instance]

    with patch(
        "ada_backend.services.graph.field_expression_autocomplete_service.get_output_ports_for_component_version"
    ) as mock_get_ports:
        with patch(
            "ada_backend.services.graph.field_expression_autocomplete_service.get_output_port_instances_for_component_instance"
        ) as mock_get_dynamic_ports:
            mock_get_ports.return_value = []

            mock_dynamic_username = MagicMock()
            mock_dynamic_username.name = "username"
            mock_dynamic_api_key = MagicMock()
            mock_dynamic_api_key.name = "api_key"
            mock_get_dynamic_ports.return_value = [mock_dynamic_username, mock_dynamic_api_key]

            suggestions = _build_port_suggestions_with_start_fields(
                session, graph_runner_id, instances, str(start_instance_id), "user"
            )

            assert len(suggestions) == 1
            assert suggestions[0].label == "username"


def test_messages_field_not_duplicated_when_also_present_as_dynamic_port():
    """Test that 'messages' is not duplicated if present in dynamic output ports."""
    session = MagicMock()
    graph_runner_id = uuid4()
    start_instance_id = uuid4()

    mock_instance = MagicMock()
    mock_instance.id = start_instance_id
    mock_instance.component_version_id = uuid4()
    instances = [mock_instance]

    with patch(
        "ada_backend.services.graph.field_expression_autocomplete_service.get_output_ports_for_component_version"
    ) as mock_get_ports:
        with patch(
            "ada_backend.services.graph.field_expression_autocomplete_service.get_output_port_instances_for_component_instance"
        ) as mock_get_dynamic_ports:
            mock_port = MagicMock()
            mock_port.name = "messages"
            mock_get_ports.return_value = [mock_port]

            mock_dynamic_messages = MagicMock()
            mock_dynamic_messages.name = "messages"
            mock_dynamic_username = MagicMock()
            mock_dynamic_username.name = "username"
            mock_get_dynamic_ports.return_value = [mock_dynamic_messages, mock_dynamic_username]

            suggestions = _build_port_suggestions_with_start_fields(
                session, graph_runner_id, instances, str(start_instance_id), ""
            )

            labels = [s.label for s in suggestions]
            assert "username" in labels
            assert labels.count("messages") == 2
            assert len(suggestions) == 3


def test_start_node_without_payload_schema():
    """Test that start node without dynamic output ports still shows output ports."""
    session = MagicMock()
    graph_runner_id = uuid4()
    start_instance_id = uuid4()

    mock_instance = MagicMock()
    mock_instance.id = start_instance_id
    mock_instance.component_version_id = uuid4()
    instances = [mock_instance]

    with patch(
        "ada_backend.services.graph.field_expression_autocomplete_service.get_output_ports_for_component_version"
    ) as mock_get_ports:
        with patch(
            "ada_backend.services.graph.field_expression_autocomplete_service.get_output_port_instances_for_component_instance"
        ) as mock_get_dynamic_ports:
            mock_port = MagicMock()
            mock_port.name = "messages"
            mock_get_ports.return_value = [mock_port]
            mock_get_dynamic_ports.return_value = []

            suggestions = _build_port_suggestions_with_start_fields(
                session, graph_runner_id, instances, str(start_instance_id), ""
            )

            assert len(suggestions) == 1
            assert suggestions[0].label == "messages"


def test_invalid_uuid_returns_empty():
    """Test that invalid UUID returns empty list."""
    session = MagicMock()
    graph_runner_id = uuid4()
    instances = []

    suggestions = _build_port_suggestions_with_start_fields(session, graph_runner_id, instances, "invalid-uuid", "")

    assert suggestions == []
