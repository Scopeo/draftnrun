from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.component_definition_seeding import (
    upsert_component_categories,
    upsert_component_versions,
    upsert_components,
    upsert_components_parameter_definitions,
    upsert_release_stage_to_current_version_mapping,
)
from ada_backend.database.models import (
    Component,
    ComponentParameterDefinition,
    ParameterType,
    UIComponent,
    UIComponentProperties,
)
from ada_backend.database.seed.seed_categories import CATEGORY_UUIDS
from ada_backend.database.seed.seed_tool_description import TOOL_DESCRIPTION_UUIDS
from ada_backend.database.seed.utils import COMPONENT_UUIDS, COMPONENT_VERSION_UUIDS


def seed_remote_mcp_tool_components(session: Session):
    remote_mcp_component = Component(
        id=COMPONENT_UUIDS["remote_mcp_tool"],
        name="MCP",
        is_agent=False,
        function_callable=True,
        can_use_function_calling=False,
        icon="tabler-cloud",
    )
    upsert_components(session, [remote_mcp_component])

    remote_mcp_component_version = db.ComponentVersion(
        id=COMPONENT_VERSION_UUIDS["remote_mcp_tool"],
        component_id=COMPONENT_UUIDS["remote_mcp_tool"],
        version_tag="0.0.1",
        release_stage=db.ReleaseStage.INTERNAL,
        description="Expose tools from a remote MCP server over HTTP.",
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["remote_mcp_tool_description"],
    )
    upsert_component_versions(session, [remote_mcp_component_version])

    parameter_definitions = [
        ComponentParameterDefinition(
            id=UUID("9c1b1c80-4b1c-4d3c-9a7e-5b7a2db4f0a1"),
            component_version_id=remote_mcp_component_version.id,
            name="server_url",
            type=ParameterType.STRING,
            nullable=False,
            ui_component=UIComponent.TEXTFIELD,
            ui_component_properties=UIComponentProperties(
                label="MCP Server URL",
                placeholder="https://api.example.com/mcp",
            ).model_dump(exclude_unset=True, exclude_none=True),
        ),
        ComponentParameterDefinition(
            id=UUID("1b6f3d14-8c31-4f08-9a53-8f7adf75b8d7"),
            component_version_id=remote_mcp_component_version.id,
            name="headers",
            type=ParameterType.STRING,
            nullable=True,
            ui_component=UIComponent.TEXTAREA,
            ui_component_properties=UIComponentProperties(
                label="Headers",
                placeholder='{"Authorization": "Bearer <token>"}',
            ).model_dump(exclude_unset=True, exclude_none=True),
        ),
    ]
    upsert_components_parameter_definitions(session, parameter_definitions)
    upsert_component_categories(
        session=session,
        component_id=remote_mcp_component.id,
        category_ids=[CATEGORY_UUIDS["action"], CATEGORY_UUIDS["query"]],
    )
    upsert_release_stage_to_current_version_mapping(
        session=session,
        component_id=remote_mcp_component_version.component_id,
        release_stage=remote_mcp_component_version.release_stage,
        component_version_id=remote_mcp_component_version.id,
    )
