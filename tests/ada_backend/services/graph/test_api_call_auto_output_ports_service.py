import socket
from unittest.mock import MagicMock, patch
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

from ada_backend.database.seed.utils import COMPONENT_VERSION_UUIDS
from ada_backend.schemas.parameter_schema import ParameterKind, PipelineParameterV2Schema
from ada_backend.schemas.pipeline.port_instance_schema import FieldExpressionSchema, InputPortInstanceSchema
from ada_backend.services.graph.api_call_auto_output_ports_service import (
    _detect_get_response_output_port_names,
)
from ada_backend.services.graph.api_call_auto_output_ports_service import (
    test_and_persist_api_call_get_auto_output_ports as call_test_and_persist_api_call_get_auto_output_ports,
)


def test_test_and_persist_api_call_get_auto_output_ports_requires_generic_api_call_component():
    session = MagicMock()
    project_id = uuid4()
    instance_id = uuid4()
    db_instance = MagicMock()
    db_instance.component_version_id = uuid4()

    with patch(
        "ada_backend.services.graph.api_call_auto_output_ports_service.get_component_instance_by_id",
        return_value=db_instance,
    ):
        try:
            call_test_and_persist_api_call_get_auto_output_ports(session, project_id, instance_id, [])
        except ValueError as e:
            assert "generic API Call" in str(e)
        else:
            raise AssertionError("Expected ValueError")


def test_test_and_persist_api_call_get_auto_output_ports_persists_manual_probe_result():
    session = MagicMock()
    project_id = uuid4()
    organization_id = uuid4()
    instance_id = uuid4()
    db_instance = MagicMock()
    db_instance.component_version_id = COMPONENT_VERSION_UUIDS["api_call_tool"]
    project = MagicMock(organization_id=organization_id)
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
        patch("ada_backend.services.graph.api_call_auto_output_ports_service.get_project", return_value=project),
        patch("ada_backend.services.graph.api_call_auto_output_ports_service.resolve_variables", return_value={}),
        patch(
            "ada_backend.services.graph.api_call_auto_output_ports_service.get_organization_secrets_from_project_id",
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
        result = call_test_and_persist_api_call_get_auto_output_ports(session, project_id, instance_id, parameters)

    assert result == ["email", "id"]
    assert [call.kwargs["name"] for call in mock_get_or_create.call_args_list] == ["email", "id"]


def test_test_and_persist_api_call_get_auto_output_ports_rejects_unsaved_probe_config():
    session = MagicMock()
    project_id = uuid4()
    organization_id = uuid4()
    instance_id = uuid4()
    db_instance = MagicMock()
    db_instance.component_version_id = COMPONENT_VERSION_UUIDS["api_call_tool"]
    project = MagicMock(organization_id=organization_id)
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
        patch("ada_backend.services.graph.api_call_auto_output_ports_service.get_project", return_value=project),
        patch("ada_backend.services.graph.api_call_auto_output_ports_service.resolve_variables", return_value={}),
        patch(
            "ada_backend.services.graph.api_call_auto_output_ports_service.get_organization_secrets_from_project_id",
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
            call_test_and_persist_api_call_get_auto_output_ports(session, project_id, instance_id, parameters)
        except ValueError as e:
            assert "Save the API Call configuration" in str(e)
        else:
            raise AssertionError("Expected ValueError")

    mock_detect.assert_not_called()
    mock_get_or_create.assert_not_called()


def test_test_and_persist_api_call_get_auto_output_ports_raises_on_manual_probe_failure():
    session = MagicMock()
    project_id = uuid4()
    organization_id = uuid4()
    instance_id = uuid4()
    db_instance = MagicMock()
    db_instance.component_version_id = COMPONENT_VERSION_UUIDS["api_call_tool"]
    project = MagicMock(organization_id=organization_id)
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
        patch("ada_backend.services.graph.api_call_auto_output_ports_service.get_project", return_value=project),
        patch("ada_backend.services.graph.api_call_auto_output_ports_service.resolve_variables", return_value={}),
        patch(
            "ada_backend.services.graph.api_call_auto_output_ports_service.get_organization_secrets_from_project_id",
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
        patch("ada_backend.services.graph.api_call_auto_output_ports_service.socket.getaddrinfo") as mock_getaddrinfo,
        patch("ada_backend.services.graph.api_call_auto_output_ports_service.httpx.Client") as mock_client_class,
        patch(
            "ada_backend.services.graph.api_call_auto_output_ports_service.get_or_create_output_port_instance"
        ) as mock_get_or_create,
    ):
        real_client = httpx.Client()
        response = MagicMock()
        response.raise_for_status.side_effect = ValueError("bad status")
        mock_getaddrinfo.return_value = [(None, None, None, None, ("93.184.216.34", 443))]
        client = mock_client_class.return_value.__enter__.return_value
        client.build_request.side_effect = real_client.build_request
        client.send.return_value = response

        try:
            call_test_and_persist_api_call_get_auto_output_ports(session, project_id, instance_id, parameters)
        except ValueError as e:
            assert "endpoint probe failed" in str(e)
        else:
            raise AssertionError("Expected ValueError")

    mock_get_or_create.assert_not_called()


def test_test_and_persist_api_call_get_auto_output_ports_resolves_secret_variables_for_probe():
    session = MagicMock()
    project_id = uuid4()
    organization_id = uuid4()
    instance_id = uuid4()
    db_instance = MagicMock()
    db_instance.component_version_id = COMPONENT_VERSION_UUIDS["api_call_tool"]
    project = MagicMock(organization_id=organization_id)

    with (
        patch(
            "ada_backend.services.graph.api_call_auto_output_ports_service.get_component_instance_by_id",
            return_value=db_instance,
        ),
        patch(
            "ada_backend.services.graph.api_call_auto_output_ports_service.get_component_basic_parameters",
            return_value=[],
        ),
        patch("ada_backend.services.graph.api_call_auto_output_ports_service.get_project", return_value=project),
        patch(
            "ada_backend.services.graph.api_call_auto_output_ports_service.resolve_variables",
            return_value={"api_headers": {"Authorization": SecretStr("Bearer secret-token")}},
        ) as mock_resolve_variables,
        patch(
            "ada_backend.services.graph.api_call_auto_output_ports_service.get_organization_secrets_from_project_id",
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
                ),
                InputPortInstanceSchema(
                    name="headers",
                    field_expression=FieldExpressionSchema(expression_json={"type": "var", "name": "api_headers"}),
                ),
            ],
        ),
        patch(
            "ada_backend.services.graph.api_call_auto_output_ports_service._detect_get_response_output_port_names",
            return_value=["id"],
        ) as mock_detect,
        patch("ada_backend.services.graph.api_call_auto_output_ports_service.get_or_create_output_port_instance"),
    ):
        result = call_test_and_persist_api_call_get_auto_output_ports(
            session,
            project_id,
            instance_id,
            variable_set_ids=["production"],
        )

    assert result == ["id"]
    mock_resolve_variables.assert_called_once_with(session, organization_id, ["production"], project_id=project_id)
    assert mock_detect.call_args.kwargs["headers"] == {"Authorization": "Bearer secret-token"}


def test_test_and_persist_api_call_get_auto_output_ports_resolves_secret_endpoint_variables_for_probe():
    session = MagicMock()
    project_id = uuid4()
    organization_id = uuid4()
    instance_id = uuid4()
    db_instance = MagicMock()
    db_instance.component_version_id = COMPONENT_VERSION_UUIDS["api_call_tool"]
    project = MagicMock(organization_id=organization_id)

    with (
        patch(
            "ada_backend.services.graph.api_call_auto_output_ports_service.get_component_instance_by_id",
            return_value=db_instance,
        ),
        patch(
            "ada_backend.services.graph.api_call_auto_output_ports_service.get_component_basic_parameters",
            return_value=[],
        ),
        patch("ada_backend.services.graph.api_call_auto_output_ports_service.get_project", return_value=project),
        patch(
            "ada_backend.services.graph.api_call_auto_output_ports_service.resolve_variables",
            return_value={"secret_endpoint": SecretStr("https://api.example.com/users")},
        ),
        patch(
            "ada_backend.services.graph.api_call_auto_output_ports_service.get_organization_secrets_from_project_id",
            return_value=[],
        ),
        patch(
            "ada_backend.services.graph.api_call_auto_output_ports_service.get_input_port_instances_for_component_instance",
            return_value=[
                InputPortInstanceSchema(
                    name="endpoint",
                    field_expression=FieldExpressionSchema(expression_json={"type": "var", "name": "secret_endpoint"}),
                )
            ],
        ),
        patch(
            "ada_backend.services.graph.api_call_auto_output_ports_service._detect_get_response_output_port_names",
            return_value=["id"],
        ) as mock_detect,
        patch("ada_backend.services.graph.api_call_auto_output_ports_service.get_or_create_output_port_instance"),
    ):
        result = call_test_and_persist_api_call_get_auto_output_ports(
            session,
            project_id,
            instance_id,
            variable_set_ids=["production"],
        )

    assert result == ["id"]
    assert mock_detect.call_args.kwargs["endpoint"] == "https://api.example.com/users"


def test_test_and_persist_api_call_get_auto_output_ports_uses_test_values_for_refs():
    session = MagicMock()
    project_id = uuid4()
    organization_id = uuid4()
    instance_id = uuid4()
    upstream_id = uuid4()
    db_instance = MagicMock()
    db_instance.component_version_id = COMPONENT_VERSION_UUIDS["api_call_tool"]
    project = MagicMock(organization_id=organization_id)

    with (
        patch(
            "ada_backend.services.graph.api_call_auto_output_ports_service.get_component_instance_by_id",
            return_value=db_instance,
        ),
        patch(
            "ada_backend.services.graph.api_call_auto_output_ports_service.get_component_basic_parameters",
            return_value=[],
        ),
        patch("ada_backend.services.graph.api_call_auto_output_ports_service.get_project", return_value=project),
        patch("ada_backend.services.graph.api_call_auto_output_ports_service.resolve_variables", return_value={}),
        patch(
            "ada_backend.services.graph.api_call_auto_output_ports_service.get_organization_secrets_from_project_id",
            return_value=[],
        ),
        patch(
            "ada_backend.services.graph.api_call_auto_output_ports_service.get_input_port_instances_for_component_instance",
            return_value=[
                InputPortInstanceSchema(
                    name="endpoint",
                    field_expression=FieldExpressionSchema(
                        expression_json={"type": "ref", "instance": str(upstream_id), "port": "url"}
                    ),
                ),
                InputPortInstanceSchema(
                    name="fixed_parameters",
                    field_expression=FieldExpressionSchema(
                        expression_json={"type": "literal", "value": '{"account_id": "acct_123"}'}
                    ),
                ),
            ],
        ),
        patch(
            "ada_backend.services.graph.api_call_auto_output_ports_service._detect_get_response_output_port_names",
            return_value=["email"],
        ) as mock_detect,
        patch("ada_backend.services.graph.api_call_auto_output_ports_service.get_or_create_output_port_instance"),
    ):
        result = call_test_and_persist_api_call_get_auto_output_ports(
            session,
            project_id,
            instance_id,
            test_values={f"{upstream_id}.url": "https://api.example.com/users/{account_id}"},
        )

    assert result == ["email"]
    assert mock_detect.call_args.kwargs["endpoint"] == "https://api.example.com/users/{account_id}"
    assert mock_detect.call_args.kwargs["fixed_parameters"] == {"account_id": "acct_123"}


def test_test_and_persist_api_call_get_auto_output_ports_accepts_saved_text_expression_probe_config():
    session = MagicMock()
    project_id = uuid4()
    organization_id = uuid4()
    instance_id = uuid4()
    upstream_id = uuid4()
    db_instance = MagicMock()
    db_instance.component_version_id = COMPONENT_VERSION_UUIDS["api_call_tool"]
    project = MagicMock(organization_id=organization_id)
    parameters = [
        PipelineParameterV2Schema(name="method", value="GET"),
        PipelineParameterV2Schema(name="endpoint", kind=ParameterKind.INPUT, value=f"@{{{{{upstream_id}.url}}}}"),
        PipelineParameterV2Schema(
            name="fixed_parameters", kind=ParameterKind.INPUT, value='{"account_id": "acct_123"}'
        ),
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
        patch("ada_backend.services.graph.api_call_auto_output_ports_service.get_project", return_value=project),
        patch("ada_backend.services.graph.api_call_auto_output_ports_service.resolve_variables", return_value={}),
        patch(
            "ada_backend.services.graph.api_call_auto_output_ports_service.get_organization_secrets_from_project_id",
            return_value=[],
        ),
        patch(
            "ada_backend.services.graph.api_call_auto_output_ports_service.get_input_port_instances_for_component_instance",
            return_value=[
                InputPortInstanceSchema(
                    name="endpoint",
                    field_expression=FieldExpressionSchema(
                        expression_json={"type": "ref", "instance": str(upstream_id), "port": "url"}
                    ),
                ),
                InputPortInstanceSchema(
                    name="fixed_parameters",
                    field_expression=FieldExpressionSchema(
                        expression_json={"type": "literal", "value": '{"account_id": "acct_123"}'}
                    ),
                ),
            ],
        ),
        patch(
            "ada_backend.services.graph.api_call_auto_output_ports_service._detect_get_response_output_port_names",
            return_value=["email"],
        ) as mock_detect,
        patch("ada_backend.services.graph.api_call_auto_output_ports_service.get_or_create_output_port_instance"),
    ):
        result = call_test_and_persist_api_call_get_auto_output_ports(
            session,
            project_id,
            instance_id,
            parameters=parameters,
            test_values={f"{upstream_id}.url": "https://api.example.com/users/{account_id}"},
        )

    assert result == ["email"]
    assert mock_detect.call_args.kwargs["endpoint"] == "https://api.example.com/users/{account_id}"
    assert mock_detect.call_args.kwargs["fixed_parameters"] == {"account_id": "acct_123"}


def test_test_and_persist_api_call_get_auto_output_ports_rejects_unsaved_text_expression_probe_config():
    session = MagicMock()
    project_id = uuid4()
    organization_id = uuid4()
    instance_id = uuid4()
    upstream_id = uuid4()
    db_instance = MagicMock()
    db_instance.component_version_id = COMPONENT_VERSION_UUIDS["api_call_tool"]
    project = MagicMock(organization_id=organization_id)
    parameters = [
        PipelineParameterV2Schema(name="method", value="GET"),
        PipelineParameterV2Schema(name="endpoint", kind=ParameterKind.INPUT, value=f"@{{{{{upstream_id}.url}}}}"),
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
        patch("ada_backend.services.graph.api_call_auto_output_ports_service.get_project", return_value=project),
        patch("ada_backend.services.graph.api_call_auto_output_ports_service.resolve_variables", return_value={}),
        patch(
            "ada_backend.services.graph.api_call_auto_output_ports_service.get_organization_secrets_from_project_id",
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
    ):
        with pytest.raises(ValueError, match="Save the API Call configuration"):
            call_test_and_persist_api_call_get_auto_output_ports(
                session,
                project_id,
                instance_id,
                parameters=parameters,
                test_values={f"{upstream_id}.url": "https://api.example.com/draft"},
            )

    mock_detect.assert_not_called()


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://127.0.0.1:8000/admin",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]/admin",
    ],
)
def test_detect_get_response_output_port_names_rejects_disallowed_probe_addresses(endpoint):
    with patch("ada_backend.services.graph.api_call_auto_output_ports_service.httpx.Client") as mock_client_class:
        with pytest.raises(ValueError, match="endpoint probe failed") as exc_info:
            _detect_get_response_output_port_names(endpoint, {}, {})

    assert "disallowed address" in str(exc_info.value)
    mock_client_class.return_value.__enter__.return_value.send.assert_not_called()


def test_detect_get_response_output_port_names_rejects_hostnames_resolving_to_private_addresses():
    with (
        patch(
            "ada_backend.services.graph.api_call_auto_output_ports_service.socket.getaddrinfo",
            return_value=[(None, None, None, None, ("10.0.0.5", 443))],
        ) as mock_getaddrinfo,
        patch("ada_backend.services.graph.api_call_auto_output_ports_service.httpx.Client") as mock_client_class,
    ):
        with pytest.raises(ValueError, match="endpoint probe failed") as exc_info:
            _detect_get_response_output_port_names("https://internal.example.com/users", {}, {})

    assert "disallowed address" in str(exc_info.value)
    mock_getaddrinfo.assert_called_once_with("internal.example.com", None, type=socket.SOCK_STREAM)
    mock_client_class.return_value.__enter__.return_value.send.assert_not_called()


def test_detect_get_response_output_port_names_uses_validated_public_ip_request():
    real_client = httpx.Client()
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"id": 123, "email": "user@example.com", "data": {"ignored": True}}

    with (
        patch(
            "ada_backend.services.graph.api_call_auto_output_ports_service.socket.getaddrinfo",
            return_value=[(None, None, None, None, ("93.184.216.34", 443))],
        ) as mock_getaddrinfo,
        patch("ada_backend.services.graph.api_call_auto_output_ports_service.httpx.Client") as mock_client_class,
    ):
        client = mock_client_class.return_value.__enter__.return_value
        client.build_request.side_effect = real_client.build_request
        client.send.return_value = response

        result = _detect_get_response_output_port_names(
            "https://api.example.com/users/{account_id}",
            {"Authorization": "Bearer token"},
            {"account_id": "acct_123", "active": True},
        )

    request = client.send.call_args.args[0]
    assert result == ["email", "id"]
    assert str(request.url) == "https://93.184.216.34/users/acct_123?active=true"
    assert request.headers["host"] == "api.example.com"
    assert request.headers["authorization"] == "Bearer token"
    assert request.extensions["sni_hostname"] == "api.example.com"
    mock_getaddrinfo.assert_called_once_with("api.example.com", None, type=socket.SOCK_STREAM)
