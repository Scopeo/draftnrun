"""Unit tests for start field autocomplete feature."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from ada_backend.schemas.pipeline.field_expression_schema import SuggestionKind
from ada_backend.services.graph.field_expression_autocomplete_service import _build_port_suggestions_with_start_fields


def test_start_node_includes_input_fields_as_properties():
    """Test that start node fields from payload_schema are included as property suggestions."""
    session = MagicMock()
    graph_runner_id = uuid4()
    start_instance_id = uuid4()

    # Mock instance
    mock_instance = MagicMock()
    mock_instance.id = start_instance_id
    mock_instance.component_version_id = uuid4()
    instances = [mock_instance]

    # Mock GraphRunnerNode query to return is_start_node=True
    mock_graph_runner_node = MagicMock()
    mock_graph_runner_node.is_start_node = True
    session.query.return_value.filter.return_value.first.return_value = mock_graph_runner_node

    with patch(
        "ada_backend.services.graph.field_expression_autocomplete_service.get_component_instance"
    ) as mock_get_instance:
        with patch(
            "ada_backend.services.graph.field_expression_autocomplete_service.extract_playground_schema_from_component"
        ) as mock_extract:
            with patch(
                "ada_backend.services.graph.field_expression_autocomplete_service.get_output_ports_for_component_version"
            ) as mock_get_ports:
                mock_extract.return_value = {
                    "messages": [{"role": "user", "content": "Hello"}],
                    "username": "John",
                    "api_key": "test-key",
                }

                mock_port = MagicMock()
                mock_port.name = "messages"
                mock_get_ports.return_value = [mock_port]

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

    # Mock GraphRunnerNode query to return is_start_node=False
    mock_graph_runner_node = MagicMock()
    mock_graph_runner_node.is_start_node = False
    session.query.return_value.filter.return_value.first.return_value = mock_graph_runner_node

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
    """Test that query filtering works for start field properties."""
    session = MagicMock()
    graph_runner_id = uuid4()
    start_instance_id = uuid4()

    mock_instance = MagicMock()
    mock_instance.id = start_instance_id
    mock_instance.component_version_id = uuid4()
    instances = [mock_instance]

    mock_graph_runner_node = MagicMock()
    mock_graph_runner_node.is_start_node = True
    session.query.return_value.filter.return_value.first.return_value = mock_graph_runner_node

    with patch("ada_backend.services.graph.field_expression_autocomplete_service.get_component_instance"):
        with patch(
            "ada_backend.services.graph.field_expression_autocomplete_service.extract_playground_schema_from_component"
        ) as mock_extract:
            with patch(
                "ada_backend.services.graph.field_expression_autocomplete_service.get_output_ports_for_component_version"
            ) as mock_get_ports:
                mock_extract.return_value = {"username": "John", "api_key": "key"}
                mock_get_ports.return_value = []

                suggestions = _build_port_suggestions_with_start_fields(
                    session, graph_runner_id, instances, str(start_instance_id), "user"
                )

                assert len(suggestions) == 1
                assert suggestions[0].label == "username"


def test_messages_field_excluded_from_input_fields():
    """Test that 'messages' field from payload_schema is excluded."""
    session = MagicMock()
    graph_runner_id = uuid4()
    start_instance_id = uuid4()

    mock_instance = MagicMock()
    mock_instance.id = start_instance_id
    mock_instance.component_version_id = uuid4()
    instances = [mock_instance]

    mock_graph_runner_node = MagicMock()
    mock_graph_runner_node.is_start_node = True
    session.query.return_value.filter.return_value.first.return_value = mock_graph_runner_node

    with patch("ada_backend.services.graph.field_expression_autocomplete_service.get_component_instance"):
        with patch(
            "ada_backend.services.graph.field_expression_autocomplete_service.extract_playground_schema_from_component"
        ) as mock_extract:
            with patch(
                "ada_backend.services.graph.field_expression_autocomplete_service.get_output_ports_for_component_version"
            ) as mock_get_ports:
                mock_extract.return_value = {"messages": [{"role": "user", "content": "Hello"}], "username": "John"}

                mock_port = MagicMock()
                mock_port.name = "messages"
                mock_get_ports.return_value = [mock_port]

                suggestions = _build_port_suggestions_with_start_fields(
                    session, graph_runner_id, instances, str(start_instance_id), ""
                )

                labels = [s.label for s in suggestions]
                assert "username" in labels
                assert labels.count("messages") == 1  # Only from output port
                assert len(suggestions) == 2


def test_start_node_without_payload_schema():
    """Test that start node without payload_schema still shows output ports."""
    session = MagicMock()
    graph_runner_id = uuid4()
    start_instance_id = uuid4()

    mock_instance = MagicMock()
    mock_instance.id = start_instance_id
    mock_instance.component_version_id = uuid4()
    instances = [mock_instance]

    mock_graph_runner_node = MagicMock()
    mock_graph_runner_node.is_start_node = True
    session.query.return_value.filter.return_value.first.return_value = mock_graph_runner_node

    with patch("ada_backend.services.graph.field_expression_autocomplete_service.get_component_instance"):
        with patch(
            "ada_backend.services.graph.field_expression_autocomplete_service.extract_playground_schema_from_component"
        ) as mock_extract:
            with patch(
                "ada_backend.services.graph.field_expression_autocomplete_service.get_output_ports_for_component_version"
            ) as mock_get_ports:
                mock_extract.return_value = None

                mock_port = MagicMock()
                mock_port.name = "messages"
                mock_get_ports.return_value = [mock_port]

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
