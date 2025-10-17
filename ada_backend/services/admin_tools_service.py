import json
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.repositories.component_repository import (
    upsert_tool_description,
    upsert_component_instance,
    get_component_parameter_definition_by_component_id,
    delete_component_global_parameters,
    upsert_specific_api_component_with_defaults,
    set_component_default_tool_description,
    insert_component_global_parameter,
    get_component_instance_by_id,
    get_component_by_id,
    get_global_parameters_by_component_id,
    get_tool_description_by_id,
    get_api_tool_components,
    check_component_used_in_projects,
)
from ada_backend.schemas.admin_tools_schema import (
    CreateSpecificApiToolRequest,
    CreatedSpecificApiToolResponse,
    ApiToolListItem,
    ApiToolListResponse,
    ApiToolDetailResponse,
)
from ada_backend.services.components_service import delete_component_service


def _serialize_optional_json(value: Optional[dict]) -> Optional[str]:
    if value is None:
        return None
    return json.dumps(value, indent=0)


def create_specific_api_tool_service(
    session: Session, payload: CreateSpecificApiToolRequest
) -> CreatedSpecificApiToolResponse:
    """
    Create a preconfigured API tool as a component.
    Each tool gets its own unique Component.
    """

    # Create component with parameters (component_id=None ensures new component is created)
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
        component_id=None,  # None = create new component
    )

    # Create new tool description (force_create=True ensures unique tool description per API tool)
    tool_desc = upsert_tool_description(
        session=session,
        name=payload.tool_description_name,
        description=(payload.tool_description or payload.tool_display_name),
        tool_properties=payload.tool_properties or {},
        required_tool_properties=payload.required_tool_properties or [],
        force_create=True,  # Always create new, never reuse by name
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


def list_api_tools_service(session: Session) -> ApiToolListResponse:
    """
    List all API tools created with the builder.
    Filters by base_component = "API Call" but excludes the original API Call component.
    """
    results = get_api_tool_components(session)

    tools = []
    for row in results:
        # Get method from global parameters
        method = None
        global_params = get_global_parameters_by_component_id(session, row.component_id)
        param_defs = get_component_parameter_definition_by_component_id(session, row.component_id)
        param_def_by_id = {p.id: p for p in param_defs}

        for param in global_params:
            param_def = param_def_by_id.get(param.parameter_definition_id)
            if param_def and param_def.name == "method":
                method = param.value
                break

        tools.append(
            ApiToolListItem(
                component_instance_id=row.component_instance_id,
                name=row.name,
                description=row.description,
                method=method,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
        )

    return ApiToolListResponse(tools=tools)


def get_api_tool_detail_service(session: Session, component_instance_id: UUID) -> ApiToolDetailResponse:
    """
    Get detailed information about a specific API tool for editing.
    """
    instance = get_component_instance_by_id(session, component_instance_id)
    if not instance:
        raise ValueError(f"Component instance {component_instance_id} not found")

    component = get_component_by_id(session, instance.component_id)
    if not component:
        raise ValueError(f"Component {instance.component_id} not found")

    tool_desc = get_tool_description_by_id(session, instance.tool_description_id)
    if not tool_desc:
        raise ValueError(f"Tool description {instance.tool_description_id} not found")

    # Get global parameters
    global_params = get_global_parameters_by_component_id(session, component.id)
    param_defs = get_component_parameter_definition_by_component_id(session, component.id)
    param_def_by_id = {p.id: p for p in param_defs}

    # Extract values
    endpoint = None
    method = None
    headers = None
    timeout = None
    fixed_parameters = None

    for param in global_params:
        param_def = param_def_by_id.get(param.parameter_definition_id)
        if not param_def:
            continue

        if param_def.name == "endpoint":
            endpoint = param.value
        elif param_def.name == "method":
            method = param.value
        elif param_def.name == "headers":
            if param.value:
                headers = json.loads(param.value)
        elif param_def.name == "timeout":
            if param.value:
                timeout = int(param.value)
        elif param_def.name == "fixed_parameters":
            if param.value:
                fixed_parameters = json.loads(param.value)

    return ApiToolDetailResponse(
        component_instance_id=instance.id,
        component_id=component.id,
        tool_description_id=tool_desc.id,
        tool_display_name=instance.name,  # User-facing name, not Component.name (internal with UUID)
        endpoint=endpoint or "",
        method=method or "GET",
        headers=headers,
        timeout=timeout,
        fixed_parameters=fixed_parameters,
        tool_description_name=tool_desc.name,
        tool_description=tool_desc.description,
        tool_properties=tool_desc.tool_properties,
        required_tool_properties=tool_desc.required_tool_properties,
    )


def update_api_tool_service(
    session: Session, component_instance_id: UUID, payload: CreateSpecificApiToolRequest
) -> CreatedSpecificApiToolResponse:
    """
    Update an existing API tool.
    Uses component ID to update the existing component instead of creating a new one.
    """
    instance = get_component_instance_by_id(session, component_instance_id)
    if not instance:
        raise ValueError(f"Component instance {component_instance_id} not found")

    if not instance.tool_description_id:
        raise ValueError(f"Component instance {component_instance_id} has no tool description")

    # Update component using component_id (repository handles the update)
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
        component_id=instance.component_id,  # Pass existing component_id to update
    )

    # Update tool description
    tool_desc = upsert_tool_description(
        session=session,
        id=instance.tool_description_id,
        name=payload.tool_description_name,
        description=payload.tool_description or payload.tool_display_name,
        tool_properties=payload.tool_properties or {},
        required_tool_properties=payload.required_tool_properties or [],
    )

    # Update instance name
    instance.name = payload.tool_display_name

    # Update component default tool description
    set_component_default_tool_description(session, component.id, tool_desc.id)

    # Update global parameters
    delete_component_global_parameters(session, component.id)

    param_defs = get_component_parameter_definition_by_component_id(session, component.id)
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

    session.commit()

    return CreatedSpecificApiToolResponse(
        component_instance_id=instance.id,
        name=instance.name,
        tool_description_id=tool_desc.id,
    )


def delete_api_tool_service(session: Session, component_instance_id: UUID) -> None:
    """
    Delete an API tool by deleting its component.
    Uses the existing delete_component_service which handles cascading deletes.
    Raises ValueError if the component is currently used in any project.
    """
    instance = get_component_instance_by_id(session, component_instance_id)
    if not instance:
        raise ValueError(f"Component instance {component_instance_id} not found")

    # Check if the component is used in any project
    if check_component_used_in_projects(session, instance.component_id):
        component = get_component_by_id(session, instance.component_id)
        component_name = component.name if component else "this component"
        raise ValueError(
            f"Cannot delete {component_name} because it is currently being used in one or more projects. "
            "Please remove it from all projects before deleting."
        )

    delete_component_service(session, instance.component_id)
