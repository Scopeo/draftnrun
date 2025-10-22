import json
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy.orm import Session
from sqlalchemy import func

from ada_backend.database import models as db
from ada_backend.database.models import ReleaseStage
from ada_backend.database.seed.utils import COMPONENT_UUIDS
from ada_backend.repositories.component_repository import (
    upsert_tool_description,
    upsert_component_instance,
    get_component_parameter_definition_by_component_id,
    delete_component_global_parameters,
    set_component_default_tool_description,
    insert_component_global_parameter,
    get_component_instance_by_id,
    get_component_by_id,
    get_tool_description_by_id,
    get_api_tool_components,
    check_component_used_in_projects,
    create_component,
    delete_component_instances,
    check_component_instance_used_in_projects,
)
from ada_backend.schemas.admin_tools_schema import (
    CreateSpecificApiToolRequest,
    CreatedSpecificApiToolResponse,
    ApiToolListItem,
    ApiToolListResponse,
    ApiToolDetailResponse,
)
from ada_backend.services.components_service import delete_component_service, update_component_service
from ada_backend.services.agent_builder_service import get_component_params


def _serialize_optional_json(value: Optional[dict]) -> Optional[str]:
    if value is None:
        return None
    return json.dumps(value, indent=0)


def _get_base_api_component_parameter_definitions(
    session: Session,
    base_component_id: UUID,
) -> dict[str, db.ComponentParameterDefinition]:
    """
    Get parameter definitions from the base API Call component.
    Returns a dictionary mapping parameter names to their definitions.
    """
    param_defs = get_component_parameter_definition_by_component_id(
        session,
        base_component_id,
    )
    return {p.name: p for p in param_defs}


def create_specific_api_tool_service(
    session: Session, payload: CreateSpecificApiToolRequest
) -> CreatedSpecificApiToolResponse:
    """
    Create a preconfigured API tool as a component.
    Each tool gets its own unique Component that inherits from the base API Call component.
    All API-specific logic is in this service layer function.
    Service only calls repository functions - no direct database operations.
    """
    headers_json = _serialize_optional_json(payload.headers)
    fixed_params_json = _serialize_optional_json(payload.fixed_parameters)

    internal_name = f"{payload.tool_display_name} [{uuid4().hex[:8]}]"

    base_component_id = COMPONENT_UUIDS["api_call_tool"]

    component = create_component(
        session=session,
        name=internal_name,
        base_component=str(base_component_id),
        description=f"Preconfigured API tool for {payload.tool_display_name}.",
        is_agent=False,
        function_callable=True,
        can_use_function_calling=False,
        release_stage=ReleaseStage.INTERNAL,
    )

    # No need to create parameter definitions - inherit from base API Call component
    # The base component already has all the parameter definitions we need

    # Create new tool description
    tool_desc = upsert_tool_description(
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

    # Get parameter definitions from the base API Call component
    param_by_name = _get_base_api_component_parameter_definitions(session, base_component_id)

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
        tool_display_name=instance.name,
        tool_description_id=tool_desc.id,
    )


def list_api_tools_service(session: Session) -> ApiToolListResponse:
    """
    List all API tools created with the builder.
    Filters by the base API Call component (legacy name or canonical UUID) while
    excluding the original base component record.
    """
    results = get_api_tool_components(session)

    tools = []
    for row in results:
        params = get_component_params(
            session,
            row.component_instance_id,
            include_global_parameters=True,
        )
        tools.append(
            ApiToolListItem(
                component_instance_id=row.component_instance_id,
                tool_display_name=row.display_name,
                description=row.description,
                method=params.get("method"),
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

    params = get_component_params(
        session,
        instance.id,
        include_global_parameters=True,
        component_instance=instance,
    )

    return ApiToolDetailResponse(
        component_instance_id=instance.id,
        component_id=component.id,
        tool_description_id=tool_desc.id,
        tool_display_name=instance.name,  # User-facing name, not Component.name (internal with UUID)
        endpoint=params.get("endpoint", "") or "",
        method=params.get("method", "GET") or "GET",
        headers=params.get("headers"),
        timeout=params.get("timeout"),
        fixed_parameters=params.get("fixed_parameters"),
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
    All API-specific logic is in this service layer function.
    Service only calls repository functions - no direct database operations.
    """
    instance = get_component_instance_by_id(session, component_instance_id)
    if not instance:
        raise ValueError(f"Component instance {component_instance_id} not found")

    if not instance.tool_description_id:
        raise ValueError(f"Component instance {component_instance_id} has no tool description")

    if payload.tool_description_id is None:
        raise ValueError("tool_description_id is required when updating an existing API tool")

    headers_json = _serialize_optional_json(payload.headers)
    fixed_params_json = _serialize_optional_json(payload.fixed_parameters)

    component = get_component_by_id(session, instance.component_id)
    if component is None:
        raise ValueError(f"Component {instance.component_id} not found")

    sibling_count = (
        session.query(func.count(db.ComponentInstance.id))
        .filter(db.ComponentInstance.component_id == component.id)
        .scalar()
    )

    base_component_id = COMPONENT_UUIDS["api_call_tool"]

    if sibling_count and sibling_count > 1:
        cloned_component = create_component(
            session=session,
            name=f"{payload.tool_display_name} [{uuid4().hex[:8]}]",
            base_component=component.base_component,
            description=f"Preconfigured API tool for {payload.tool_display_name}.",
            is_agent=component.is_agent,
            function_callable=component.function_callable,
            can_use_function_calling=component.can_use_function_calling,
            release_stage=component.release_stage,
        )
        instance.component_id = cloned_component.id
        component = cloned_component
    else:
        component = update_component_service(
            session=session,
            component_id=component.id,
            description=f"Preconfigured API tool for {payload.tool_display_name}.",
        )

    # Clear existing global parameters before setting new ones
    delete_component_global_parameters(session, component.id)
    # No need to delete parameter definitions - they come from the base component

    # Update tool description using ID from payload
    tool_desc = upsert_tool_description(
        session=session,
        id=payload.tool_description_id,
        name=payload.tool_description_name,
        description=payload.tool_description or payload.tool_display_name,
        tool_properties=payload.tool_properties or {},
        required_tool_properties=payload.required_tool_properties or [],
    )

    # Service layer handles the validation - repository returns None if not found
    if not tool_desc:
        raise ValueError(f"ToolDescription with id {payload.tool_description_id} not found")

    # Update instance name
    instance.name = payload.tool_display_name
    session.flush()

    # Update component default tool description
    set_component_default_tool_description(session, component.id, tool_desc.id)

    # Get parameter definitions from the base API Call component
    param_by_name = _get_base_api_component_parameter_definitions(session, base_component_id)

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
        tool_display_name=instance.name,
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

    if check_component_instance_used_in_projects(session, component_instance_id):
        raise ValueError(
            "Cannot delete this API tool because it is currently being used in one or more projects. "
            "Please remove it from all projects before deleting."
        )

    sibling_count = (
        session.query(func.count(db.ComponentInstance.id))
        .filter(db.ComponentInstance.component_id == instance.component_id)
        .scalar()
    )

    if sibling_count and sibling_count > 1:
        delete_component_instances(session, [component_instance_id])
        return

    # Check if the component is used in any project
    if check_component_used_in_projects(session, instance.component_id):
        component = get_component_by_id(session, instance.component_id)
        component_name = component.name if component else "this component"
        raise ValueError(
            f"Cannot delete {component_name} because it is currently being used in one or more projects. "
            "Please remove it from all projects before deleting."
        )

    delete_component_service(session, instance.component_id)
