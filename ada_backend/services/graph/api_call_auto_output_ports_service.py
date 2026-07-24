import ipaddress
import socket
import string
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

import httpx
from sqlalchemy.orm import Session

from ada_backend.database.seed.utils import COMPONENT_VERSION_UUIDS
from ada_backend.repositories.component_repository import get_component_basic_parameters, get_component_instance_by_id
from ada_backend.repositories.input_port_instance_repository import get_input_port_instances_for_component_instance
from ada_backend.repositories.output_port_instance_repository import get_or_create_output_port_instance
from ada_backend.schemas.parameter_schema import ParameterKind, PipelineParameterV2Schema
from ada_backend.schemas.pipeline.port_instance_schema import InputPortInstanceSchema
from engine.components.tools.api_call_tool import extract_api_call_response_root_outputs
from engine.components.utils import load_str_to_json

_MISSING = object()
_API_CALL_INPUT_NAMES = {"endpoint", "headers", "fixed_parameters"}
_SAVE_TIME_DETECTION_TIMEOUT_SECONDS = 5.0
_DISALLOWED_PROBE_NETWORKS = (
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("fe80::/10"),
)


def _literal_from_field_expression(field_expression: Any) -> Any:
    if field_expression is None:
        return _MISSING
    if hasattr(field_expression, "expression_json"):
        expression_json = field_expression.expression_json
    elif isinstance(field_expression, dict):
        expression_json = field_expression.get("expression_json", field_expression)
    else:
        return _MISSING
    if not isinstance(expression_json, dict) or expression_json.get("type") != "literal":
        return _MISSING
    return expression_json.get("value")


def _literal_from_parameter(param: Any) -> Any:
    if getattr(param, "value", None) is not None:
        return param.value
    return _literal_from_field_expression(getattr(param, "field_expression", None))


def _literal_from_input_port(port: InputPortInstanceSchema) -> Any:
    return _literal_from_field_expression(port.field_expression)


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
        value = _literal_from_parameter(param)
        if value is _MISSING:
            unresolved.add(name)
        else:
            values[name] = value

    for port in input_port_instances or []:
        if port.name not in _API_CALL_INPUT_NAMES:
            continue
        value = _literal_from_input_port(port)
        if value is _MISSING:
            unresolved.add(port.name)
        else:
            values[port.name] = value

    return values, unresolved


def _collect_saved_api_call_values(session: Session, component_instance_id: UUID) -> tuple[dict[str, Any], set[str]]:
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
    return _collect_api_call_save_values(basic_parameters, input_port_instances)


def _ensure_probe_uses_saved_configuration(
    request_parameters: list[Any] | None,
    saved_values: dict[str, Any],
) -> None:
    if not request_parameters:
        return

    request_values, request_unresolved = _collect_api_call_save_values(request_parameters, None)
    if request_unresolved:
        raise ValueError(f"API Call test requires literal values for: {', '.join(sorted(request_unresolved))}")

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
    host = parsed.hostname if parsed.port is None else f"{parsed.hostname}:{parsed.port}"
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
        formatted_endpoint = endpoint.strip().format(**fixed_parameters)
        formatter = string.Formatter()
        used_keys = {field_name for _, field_name, _, _ in formatter.parse(formatted_endpoint) if field_name}
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
    component_instance_id: UUID,
    parameters: list[Any] | None = None,
) -> list[str]:
    component_instance = get_component_instance_by_id(session, component_instance_id)
    if not component_instance:
        raise ValueError(f"Component instance {component_instance_id} not found")
    if component_instance.component_version_id != COMPONENT_VERSION_UUIDS["api_call_tool"]:
        raise ValueError("Output-port testing is only available for the generic API Call component")

    values, unresolved = _collect_saved_api_call_values(session, component_instance_id)
    if unresolved:
        raise ValueError(f"API Call test requires literal values for: {', '.join(sorted(unresolved))}")
    _ensure_probe_uses_saved_configuration(parameters, values)

    method = str(values.get("method") or "GET").upper()
    if method != "GET":
        raise ValueError("API Call output-port test is only available for GET requests")

    endpoint = values.get("endpoint")
    if not isinstance(endpoint, str) or not endpoint.strip():
        raise ValueError("API Call output-port test requires an endpoint")

    headers = _coerce_json_object(values.get("headers"))
    fixed_parameters = _coerce_json_object(values.get("fixed_parameters"))
    if headers is None:
        raise ValueError("API Call headers must be a JSON object")
    if fixed_parameters is None:
        raise ValueError("API Call fixed parameters must be a JSON object")

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
