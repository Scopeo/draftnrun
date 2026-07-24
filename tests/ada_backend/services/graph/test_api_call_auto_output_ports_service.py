from unittest.mock import MagicMock, patch
from uuid import uuid4

from ada_backend.database.seed.utils import COMPONENT_VERSION_UUIDS
from ada_backend.schemas.parameter_schema import ParameterKind, PipelineParameterV2Schema
from ada_backend.schemas.pipeline.port_instance_schema import FieldExpressionSchema, InputPortInstanceSchema
from ada_backend.services.graph.api_call_auto_output_ports_service import (
    test_and_persist_api_call_get_auto_output_ports as call_test_and_persist_api_call_get_auto_output_ports,
)


def test_test_and_persist_api_call_get_auto_output_ports_requires_generic_api_call_component():
    session = MagicMock()
    instance_id = uuid4()
    db_instance = MagicMock()
    db_instance.component_version_id = uuid4()

    with patch(
        "ada_backend.services.graph.api_call_auto_output_ports_service.get_component_instance_by_id",
        return_value=db_instance,
    ):
        try:
            call_test_and_persist_api_call_get_auto_output_ports(session, instance_id, [])
        except ValueError as e:
            assert "generic API Call" in str(e)
        else:
            raise AssertionError("Expected ValueError")


def test_test_and_persist_api_call_get_auto_output_ports_persists_manual_probe_result():
    session = MagicMock()
    instance_id = uuid4()
    db_instance = MagicMock()
    db_instance.component_version_id = COMPONENT_VERSION_UUIDS["api_call_tool"]
    parameters = [
        PipelineParameterV2Schema(name="method", value="GET"),
        PipelineParameterV2Schema(name="endpoint", kind=ParameterKind.INPUT, value="https://api.example.com/users"),
    ]

    with (
        patch(
            "ada_backend.services.graph.api_call_auto_output_ports_service.get_component_instance_by_id",
            return_value=db_instance,
        ),
        patch(
            "ada_backend.services.graph.api_call_auto_output_ports_service.get_component_basic_parameters",
            return_value=[],
        ),
        patch(
            "ada_backend.services.graph.api_call_auto_output_ports_service.get_input_port_instances_for_component_instance",
            return_value=[
                InputPortInstanceSchema(
                    name="endpoint",
                    field_expression=FieldExpressionSchema(
                        expression_json={"type": "literal", "value": "https://api.example.com/users"}
                    ),
                )
            ],
        ),
        patch(
            "ada_backend.services.graph.api_call_auto_output_ports_service._detect_get_response_output_port_names",
            return_value=["email", "id"],
        ),
        patch(
            "ada_backend.services.graph.api_call_auto_output_ports_service.get_or_create_output_port_instance"
        ) as mock_get_or_create,
    ):
        result = call_test_and_persist_api_call_get_auto_output_ports(session, instance_id, parameters)

    assert result == ["email", "id"]
    assert [call.kwargs["name"] for call in mock_get_or_create.call_args_list] == ["email", "id"]


def test_test_and_persist_api_call_get_auto_output_ports_rejects_unsaved_probe_config():
    session = MagicMock()
    instance_id = uuid4()
    db_instance = MagicMock()
    db_instance.component_version_id = COMPONENT_VERSION_UUIDS["api_call_tool"]
    parameters = [
        PipelineParameterV2Schema(name="method", value="GET"),
        PipelineParameterV2Schema(name="endpoint", kind=ParameterKind.INPUT, value="https://api.example.com/draft"),
    ]

    with (
        patch(
            "ada_backend.services.graph.api_call_auto_output_ports_service.get_component_instance_by_id",
            return_value=db_instance,
        ),
        patch(
            "ada_backend.services.graph.api_call_auto_output_ports_service.get_component_basic_parameters",
            return_value=[],
        ),
        patch(
            "ada_backend.services.graph.api_call_auto_output_ports_service.get_input_port_instances_for_component_instance",
            return_value=[
                InputPortInstanceSchema(
                    name="endpoint",
                    field_expression=FieldExpressionSchema(
                        expression_json={"type": "literal", "value": "https://api.example.com/saved"}
                    ),
                )
            ],
        ),
        patch(
            "ada_backend.services.graph.api_call_auto_output_ports_service._detect_get_response_output_port_names"
        ) as mock_detect,
        patch(
            "ada_backend.services.graph.api_call_auto_output_ports_service.get_or_create_output_port_instance"
        ) as mock_get_or_create,
    ):
        try:
            call_test_and_persist_api_call_get_auto_output_ports(session, instance_id, parameters)
        except ValueError as e:
            assert "Save the API Call configuration" in str(e)
        else:
            raise AssertionError("Expected ValueError")

    mock_detect.assert_not_called()
    mock_get_or_create.assert_not_called()


def test_test_and_persist_api_call_get_auto_output_ports_raises_on_manual_probe_failure():
    session = MagicMock()
    instance_id = uuid4()
    db_instance = MagicMock()
    db_instance.component_version_id = COMPONENT_VERSION_UUIDS["api_call_tool"]
    parameters = [
        PipelineParameterV2Schema(name="method", value="GET"),
        PipelineParameterV2Schema(name="endpoint", kind=ParameterKind.INPUT, value="https://api.example.com/users"),
    ]

    with (
        patch(
            "ada_backend.services.graph.api_call_auto_output_ports_service.get_component_instance_by_id",
            return_value=db_instance,
        ),
        patch(
            "ada_backend.services.graph.api_call_auto_output_ports_service.get_component_basic_parameters",
            return_value=[],
        ),
        patch(
            "ada_backend.services.graph.api_call_auto_output_ports_service.get_input_port_instances_for_component_instance",
            return_value=[
                InputPortInstanceSchema(
                    name="endpoint",
                    field_expression=FieldExpressionSchema(
                        expression_json={"type": "literal", "value": "https://api.example.com/users"}
                    ),
                )
            ],
        ),
        patch("ada_backend.services.graph.api_call_auto_output_ports_service.httpx.Client") as mock_client_class,
        patch(
            "ada_backend.services.graph.api_call_auto_output_ports_service.get_or_create_output_port_instance"
        ) as mock_get_or_create,
    ):
        response = MagicMock()
        response.raise_for_status.side_effect = ValueError("bad status")
        client = mock_client_class.return_value.__enter__.return_value
        client.get.return_value = response

        try:
            call_test_and_persist_api_call_get_auto_output_ports(session, instance_id, parameters)
        except ValueError as e:
            assert "endpoint probe failed" in str(e)
        else:
            raise AssertionError("Expected ValueError")

    mock_get_or_create.assert_not_called()
