import json
from typing import Optional

from sqlalchemy.orm import Session

from ada_backend.repositories.component_repository import (
    get_or_create_tool_description,
    upsert_component_instance,
    get_component_parameter_definition_by_component_id,
    delete_component_global_parameters,
    upsert_specific_api_component_with_defaults,
    set_component_default_tool_description,
    insert_component_global_parameter,
)
from ada_backend.schemas.admin_tools_schema import (
    CreateSpecificApiToolRequest,
    CreatedSpecificApiToolResponse,
)


def _serialize_optional_json(value: Optional[dict]) -> Optional[str]:
    if value is None:
        return None
    return json.dumps(value, indent=0)


def create_specific_api_tool_service(
    session: Session, payload: CreateSpecificApiToolRequest
) -> CreatedSpecificApiToolResponse:
    """
    Create a preconfigured API tool as a component.
    """

    # Component name is derived from the created component
    headers_json = _serialize_optional_json(payload.headers)
    fixed_params_json = _serialize_optional_json(payload.fixed_parameters)
    component = upsert_specific_api_component_with_defaults(
        session=session,
        tool_display_name=payload.tool_display_name,
        endpoint=payload.endpoint,
        method=payload.method,
        headers_json=headers_json,
        timeout_val=payload.timeout,
        fixed_params_json=fixed_params_json,
    )

    # Upsert tool description
    tool_desc = get_or_create_tool_description(
        session=session,
        name=payload.tool_description_name,
        description=(payload.tool_description or payload.tool_display_name),
        tool_properties=payload.tool_properties or {},
        required_tool_properties=payload.required_tool_properties or [],
    )
    # Ensure the component exposes this tool description as its default
    set_component_default_tool_description(session, component.id, tool_desc.id)
    # Create instance bound to chosen component
    instance = upsert_component_instance(
        session=session,
        component_id=component.id,
        name=payload.tool_display_name,
        tool_description_id=tool_desc.id,
    )

    # Reset then write global component parameters (non-overridable)
    # Ensure idempotency when recreating/updating the same tool
    delete_component_global_parameters(session, component.id)

    param_defs = get_component_parameter_definition_by_component_id(
        session,
        component.id,
    )
    param_by_name = {p.name: p for p in param_defs}

    def _insert_global(name: str, raw_value: Optional[str]) -> None:
        if raw_value is None:
            return
        insert_component_global_parameter(
            session=session,
            component_id=component.id,
            parameter_definition_id=param_by_name[name].id,
            value=raw_value,
        )

    _insert_global("endpoint", payload.endpoint)
    _insert_global("method", payload.method)
    _insert_global("headers", headers_json)
    if payload.timeout is not None:
        _insert_global("timeout", str(payload.timeout))
    _insert_global("fixed_parameters", fixed_params_json)

    # No instance-level parameters.
    # Component-level defaults carry configuration.

    return CreatedSpecificApiToolResponse(
        component_instance_id=instance.id,
        name=instance.name,
        tool_description_id=tool_desc.id,
    )
