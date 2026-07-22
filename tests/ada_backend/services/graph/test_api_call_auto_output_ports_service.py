from unittest.mock import MagicMock, patch
from uuid import uuid4

from ada_backend.database.seed.utils import COMPONENT_VERSION_UUIDS
from ada_backend.schemas.parameter_schema import ParameterKind, PipelineParameterV2Schema
from ada_backend.schemas.pipeline.port_instance_schema import FieldExpressionSchema, InputPortInstanceSchema
from ada_backend.services.graph.api_call_auto_output_ports_service import (
    persist_api_call_get_auto_output_ports,
    test_and_persist_api_call_get_auto_output_ports,
)


def test_persist_api_call_get_auto_output_ports_probes_literal_get_config():
    session = MagicMock()
    instance_id = uuid4()

    parameters = [
        PipelineParameterV2Schema(name="method", value="GET"),
        PipelineParameterV2Schema(
            name="endpoint",
            kind=ParameterKind.INPUT,
            field_expression={"expression_json": {"type": "literal", "value": "https://api.example.com/users"}},
        ),
        PipelineParameterV2Schema(name="headers", kind=ParameterKind.INPUT, value={"Authorization": "Bearer token"}),
        PipelineParameterV2Schema(
            name="fixed_parameters",
            kind=ParameterKind.INPUT,
            value={"limit": 1},
        ),
    ]

    with (
        patch("ada_backend.services.graph.api_call_auto_output_ports_service.httpx.Client") as mock_client_class,
        patch(
            "ada_backend.services.graph.api_call_auto_output_ports_service.get_or_create_output_port_instance"
        ) as mock_get_or_create,
    ):
        response = MagicMock()
        response.json.return_value = {
            "id": "user-123",
            "email": "ada@example.com",
            "success": "reserved",
            "_private": "hidden",
        }
        client = mock_client_class.return_value.__enter__.return_value
        client.get.return_value = response

        result = persist_api_call_get_auto_output_ports(
            session=session,
            component_version_id=COMPONENT_VERSION_UUIDS["api_call_tool"],
            component_instance_id=instance_id,
            parameters=parameters,
        )

    assert result == ["email", "id"]
    client.get.assert_called_once_with(
        url="https://api.example.com/users",
        headers={"Authorization": "Bearer token"},
        params={"limit": 1},
    )
    assert [call.kwargs["name"] for call in mock_get_or_create.call_args_list] == ["email", "id"]


def test_persist_api_call_get_auto_output_ports_skips_non_get_methods():
    session = MagicMock()
    instance_id = uuid4()
    parameters = [
        PipelineParameterV2Schema(name="method", value="POST"),
        PipelineParameterV2Schema(name="endpoint", kind=ParameterKind.INPUT, value="https://api.example.com/users"),
    ]

    with patch("ada_backend.services.graph.api_call_auto_output_ports_service.httpx.Client") as mock_client_class:
        result = persist_api_call_get_auto_output_ports(
            session=session,
            component_version_id=COMPONENT_VERSION_UUIDS["api_call_tool"],
            component_instance_id=instance_id,
            parameters=parameters,
        )

    assert result == []
    mock_client_class.assert_not_called()


def test_persist_api_call_get_auto_output_ports_skips_non_literal_inputs():
    session = MagicMock()
    instance_id = uuid4()
    input_ports = [
        InputPortInstanceSchema(
            name="endpoint",
            field_expression=FieldExpressionSchema(
                expression_json={"type": "ref", "instance": str(uuid4()), "port": "output"}
            ),
        )
    ]

    with patch("ada_backend.services.graph.api_call_auto_output_ports_service.httpx.Client") as mock_client_class:
        result = persist_api_call_get_auto_output_ports(
            session=session,
            component_version_id=COMPONENT_VERSION_UUIDS["api_call_tool"],
            component_instance_id=instance_id,
            parameters=[PipelineParameterV2Schema(name="method", value="GET")],
            input_port_instances=input_ports,
        )

    assert result == []
    mock_client_class.assert_not_called()


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
            test_and_persist_api_call_get_auto_output_ports(session, instance_id, [])
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
            "ada_backend.services.graph.api_call_auto_output_ports_service._detect_get_response_output_port_names",
            return_value=["email", "id"],
        ),
        patch(
            "ada_backend.services.graph.api_call_auto_output_ports_service.get_or_create_output_port_instance"
        ) as mock_get_or_create,
    ):
        result = test_and_persist_api_call_get_auto_output_ports(session, instance_id, parameters)

    assert result == ["email", "id"]
    assert [call.kwargs["name"] for call in mock_get_or_create.call_args_list] == ["email", "id"]
