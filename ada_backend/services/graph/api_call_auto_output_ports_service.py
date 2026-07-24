import ipaddress
import socket
import string
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

import httpx
from pydantic import SecretStr
from sqlalchemy.orm import Session

from ada_backend.database.seed.utils import COMPONENT_VERSION_UUIDS
from ada_backend.repositories.component_repository import get_component_basic_parameters, get_component_instance_by_id
from ada_backend.repositories.input_port_instance_repository import get_input_port_instances_for_component_instance
from ada_backend.repositories.organization_repository import get_organization_secrets_from_project_id
from ada_backend.repositories.output_port_instance_repository import get_or_create_output_port_instance
from ada_backend.repositories.project_repository import get_project
from ada_backend.schemas.parameter_schema import ParameterKind, PipelineParameterV2Schema
from ada_backend.schemas.pipeline.port_instance_schema import InputPortInstanceSchema
from ada_backend.services.variable_resolution_service import resolve_variables
from ada_backend.utils.secret_resolver import replace_secret_placeholders
from engine.components.tools.api_call_tool import extract_api_call_response_root_outputs
from engine.components.types import NodeData
from engine.components.utils import load_str_to_json
from engine.field_expressions.ast import RefNode
from engine.field_expressions.errors import FieldExpressionError
from engine.field_expressions.serializer import from_json as expression_from_json
from engine.graph_runner.field_expression_management import evaluate_expression
from engine.graph_runner.types import Task, TaskState
from engine.secret_utils import unwrap_secret

_MISSING = object()
_API_CALL_INPUT_NAMES = {"endpoint", "headers", "fixed_parameters"}
_SAVE_TIME_DETECTION_TIMEOUT_SECONDS = 5.0
_DISALLOWED_PROBE_NETWORKS = (
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("fe80::/10"),
)


def _test_value_for_ref(ref: RefNode, test_values: dict[str, Any]) -> Any:
    nested_value = test_values.get(ref.instance)
    if isinstance(nested_value, dict) and ref.port in nested_value:
        value = nested_value[ref.port]
        if ref.key and isinstance(value, dict) and ref.key in value:
            return value[ref.key]
        if ref.key:
            raise FieldExpressionError(f"Test value for '{ref.instance}.{ref.port}' does not contain key '{ref.key}'")
        return value

    candidates = []
    if ref.key:
        candidates.extend([
            f"{ref.instance}.{ref.port}::{ref.key}",
            f"{ref.instance}.{ref.port}.{ref.key}",
        ])
    candidates.append(f"{ref.instance}.{ref.port}")

    for candidate in candidates:
        if candidate in test_values:
            value = test_values[candidate]
            if ref.key and candidate == f"{ref.instance}.{ref.port}" and isinstance(value, dict) and ref.key in value:
                return value[ref.key]
            return value

    raise FieldExpressionError(f"Test value required for '{ref.instance}.{ref.port}'")


def _build_test_tasks(test_values: dict[str, Any]) -> dict[str, Task]:
    tasks: dict[str, Task] = {}
    for key, value in test_values.items():
        if isinstance(value, dict) and (not isinstance(key, str) or "." not in key):
            tasks[str(key)] = Task(
                pending_deps=0,
                state=TaskState.COMPLETED,
                result=NodeData(data=value),
            )
            continue
        if not isinstance(key, str) or "." not in key:
            continue
        instance, port = key.split(".", 1)
        if not instance or not port:
            continue
        ref_key = None
        if "::" in port:
            port, ref_key = port.split("::", 1)
        task = tasks.setdefault(
            instance,
            Task(pending_deps=0, state=TaskState.COMPLETED, result=NodeData(data={})),
        )
        if task.result:
            if ref_key:
                existing = task.result.data.setdefault(port, {})
                if isinstance(existing, dict):
                    existing[ref_key] = value
            else:
                task.result.data[port] = value
    return tasks


def _value_from_field_expression(
    field_expression: Any,
    variables: dict[str, Any] | None = None,
    test_values: dict[str, Any] | None = None,
    field_name: str = "value",
) -> Any:
    if field_expression is None:
        return _MISSING
    if hasattr(field_expression, "expression_json"):
        expression_json = field_expression.expression_json
    elif isinstance(field_expression, dict):
        expression_json = field_expression.get("expression_json", field_expression)
    else:
        return _MISSING
    if not isinstance(expression_json, dict):
        return _MISSING
    if expression_json.get("type") == "literal":
        return expression_json.get("value")
    try:
        expression = expression_from_json(expression_json)
        return evaluate_expression(
            expression,
            field_name,
            _build_test_tasks(test_values or {}),
            variables=variables,
        )
    except FieldExpressionError:
        if isinstance(expression, RefNode):
            return _test_value_for_ref(expression, test_values or {})
        return _MISSING
    except ValueError:
        return _MISSING


def _value_from_parameter(
    param: Any,
    variables: dict[str, Any] | None = None,
    test_values: dict[str, Any] | None = None,
) -> Any:
    if getattr(param, "value", None) is not None:
        return param.value
    return _value_from_field_expression(getattr(param, "field_expression", None), variables, test_values, param.name)


def _value_from_input_port(
    port: InputPortInstanceSchema,
    variables: dict[str, Any] | None = None,
    test_values: dict[str, Any] | None = None,
) -> Any:
    return _value_from_field_expression(port.field_expression, variables, test_values, port.name)


def _coerce_json_object(value: Any) -> dict[str, Any] | None:
    if value is None or value == "":
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = load_str_to_json(value)
        except ValueError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def _unwrap_probe_secrets(value: Any) -> Any:
    if isinstance(value, SecretStr):
        return unwrap_secret(value)
    if isinstance(value, dict):
        return {key: _unwrap_probe_secrets(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_unwrap_probe_secrets(item) for item in value]
    return value


def _normalize_api_call_config_values(values: dict[str, Any]) -> dict[str, Any]:
    return {
        "method": str(values.get("method") or "GET").upper(),
        "endpoint": values.get("endpoint").strip()
        if isinstance(values.get("endpoint"), str)
        else values.get("endpoint"),
        "headers": _coerce_json_object(values.get("headers")),
        "fixed_parameters": _coerce_json_object(values.get("fixed_parameters")),
    }


def _collect_api_call_save_values(
    parameters: list[Any] | None,
    input_port_instances: list[InputPortInstanceSchema] | None,
    variables: dict[str, Any] | None = None,
    test_values: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], set[str]]:
    values: dict[str, Any] = {}
    unresolved: set[str] = set()

    for param in parameters or []:
        name = getattr(param, "name", None)
        if not name:
            continue
        kind = getattr(param, "kind", ParameterKind.PARAMETER)
        if kind == ParameterKind.PARAMETER:
            values[name] = getattr(param, "value", None)
            continue
        if name not in _API_CALL_INPUT_NAMES:
            continue
        value = _value_from_parameter(param, variables, test_values)
        if value is _MISSING:
            unresolved.add(name)
        else:
            values[name] = value

    for port in input_port_instances or []:
        if port.name not in _API_CALL_INPUT_NAMES:
            continue
        value = _value_from_input_port(port, variables, test_values)
        if value is _MISSING:
            unresolved.add(port.name)
        else:
            values[port.name] = value

    return values, unresolved


def _collect_saved_api_call_values(
    session: Session,
    component_instance_id: UUID,
    variables: dict[str, Any] | None = None,
    test_values: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], set[str]]:
    basic_parameters = [
        PipelineParameterV2Schema(
            name=param.parameter_definition.name,
            value=param.get_value(),
            kind=ParameterKind.PARAMETER,
        )
        for param in get_component_basic_parameters(session, component_instance_id)
    ]
    input_port_instances = get_input_port_instances_for_component_instance(
        session,
        component_instance_id,
        eager_load_field_expression=True,
    )
    return _collect_api_call_save_values(basic_parameters, input_port_instances, variables, test_values)


def _ensure_probe_uses_saved_configuration(
    request_parameters: list[Any] | None,
    saved_values: dict[str, Any],
    variables: dict[str, Any] | None = None,
    test_values: dict[str, Any] | None = None,
) -> None:
    if not request_parameters:
        return

    request_values, request_unresolved = _collect_api_call_save_values(
        request_parameters, None, variables, test_values
    )
    if request_unresolved:
        raise ValueError(
            f"API Call test requires resolved or test values for: {', '.join(sorted(request_unresolved))}"
        )

    request_config = _normalize_api_call_config_values(request_values)
    saved_config = _normalize_api_call_config_values(saved_values)
    if request_config != saved_config:
        raise ValueError("Save the API Call configuration before testing output ports")


def _validate_probe_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"Unsupported API Call probe URL scheme: {parsed.scheme}")
    if parsed.username or parsed.password:
        raise ValueError("API Call probe URLs must not contain credentials")
    if not parsed.hostname:
        raise ValueError("API Call probe URL must include a hostname")


def _is_disallowed_probe_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or any(ip in network for network in _DISALLOWED_PROBE_NETWORKS)
    )


def _resolve_probe_ip(hostname: str, port: int | None = None) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    try:
        addr_infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as error:
        raise ValueError(f"Could not resolve API Call probe URL hostname: {hostname}") from error
    if not addr_infos:
        raise ValueError(f"Could not resolve API Call probe URL hostname: {hostname}")
    for addr_info in addr_infos:
        ip = ipaddress.ip_address(addr_info[4][0])
        if not _is_disallowed_probe_ip(ip):
            return ip
    raise ValueError(f"API Call probe URL resolves to a disallowed address: {addr_infos[0][4][0]}")


def _build_validated_probe_request(
    client: httpx.Client,
    url: str,
    headers: dict[str, Any],
    params: dict[str, Any] | None = None,
) -> httpx.Request:
    _validate_probe_url(url)
    parsed = urlparse(url)
    if not parsed.hostname:
        raise ValueError("API Call probe URL must include a hostname")
    ip = _resolve_probe_ip(parsed.hostname, parsed.port)
    host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
    if parsed.port is not None:
        host = f"{host}:{parsed.port}"
    request_host = f"[{ip}]" if isinstance(ip, ipaddress.IPv6Address) else str(ip)
    port = f":{parsed.port}" if parsed.port is not None else ""
    path = parsed.path or "/"
    query = f"?{parsed.query}" if parsed.query else ""
    request_headers = {str(key): str(value) for key, value in headers.items()}
    request_headers["Host"] = host
    request = client.build_request(
        "GET", f"{parsed.scheme}://{request_host}{port}{path}{query}", headers=request_headers, params=params
    )
    if parsed.scheme == "https":
        request.extensions["sni_hostname"] = parsed.hostname
    return request


def _detect_get_response_output_port_names(
    endpoint: str,
    headers: dict[str, Any],
    fixed_parameters: dict[str, Any],
) -> list[str]:
    try:
        formatter = string.Formatter()
        stripped_endpoint = endpoint.strip()
        used_keys = {field_name for _, field_name, _, _ in formatter.parse(stripped_endpoint) if field_name}
        formatted_endpoint = stripped_endpoint.format(**fixed_parameters)
        filtered_parameters = {key: value for key, value in fixed_parameters.items() if key not in used_keys}
        request_kwargs: dict[str, Any] = {
            "url": formatted_endpoint,
            "headers": headers,
        }
        if filtered_parameters:
            request_kwargs["params"] = filtered_parameters
        with httpx.Client(timeout=_SAVE_TIME_DETECTION_TIMEOUT_SECONDS) as client:
            response = client.send(_build_validated_probe_request(client, **request_kwargs))
            response.raise_for_status()
            response_data = response.json()
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as e:
        raise ValueError(f"API Call endpoint probe failed: {e}") from e

    if not isinstance(response_data, dict):
        return []
    return sorted(extract_api_call_response_root_outputs(response_data).keys())


def test_and_persist_api_call_get_auto_output_ports(
    session: Session,
    project_id: UUID,
    component_instance_id: UUID,
    parameters: list[Any] | None = None,
    test_values: dict[str, Any] | None = None,
    variable_set_ids: list[str] | None = None,
) -> list[str]:
    component_instance = get_component_instance_by_id(session, component_instance_id)
    if not component_instance:
        raise ValueError(f"Component instance {component_instance_id} not found")
    if component_instance.component_version_id != COMPONENT_VERSION_UUIDS["api_call_tool"]:
        raise ValueError("Output-port testing is only available for the generic API Call component")

    project = get_project(session, project_id=project_id)
    if not project:
        raise ValueError(f"Project {project_id} not found")
    org_secrets = get_organization_secrets_from_project_id(session, project_id)
    key_to_secret = {secret.key: secret.secret for secret in org_secrets}
    resolved_variables = resolve_variables(
        session,
        project.organization_id,
        variable_set_ids or [],
        project_id=project_id,
    )
    variables = {**(test_values or {}), **resolved_variables}

    values, unresolved = _collect_saved_api_call_values(session, component_instance_id, variables, test_values)
    if unresolved:
        raise ValueError(f"API Call test requires resolved or test values for: {', '.join(sorted(unresolved))}")
    _ensure_probe_uses_saved_configuration(parameters, values, variables, test_values)

    method = str(values.get("method") or "GET").upper()
    if method != "GET":
        raise ValueError("API Call output-port test is only available for GET requests")

    endpoint = _unwrap_probe_secrets(replace_secret_placeholders(values.get("endpoint"), key_to_secret))
    if not isinstance(endpoint, str) or not endpoint.strip():
        raise ValueError("API Call output-port test requires an endpoint")

    headers = _coerce_json_object(values.get("headers"))
    fixed_parameters = _coerce_json_object(values.get("fixed_parameters"))
    if headers is None:
        raise ValueError("API Call headers must be a JSON object")
    if fixed_parameters is None:
        raise ValueError("API Call fixed parameters must be a JSON object")
    headers = _unwrap_probe_secrets(replace_secret_placeholders(headers, key_to_secret))
    fixed_parameters = _unwrap_probe_secrets(replace_secret_placeholders(fixed_parameters, key_to_secret))

    port_names = _detect_get_response_output_port_names(
        endpoint=endpoint,
        headers=headers,
        fixed_parameters=fixed_parameters,
    )
    for port_name in port_names:
        get_or_create_output_port_instance(
            session=session,
            component_instance_id=component_instance_id,
            name=port_name,
        )
    return port_names
