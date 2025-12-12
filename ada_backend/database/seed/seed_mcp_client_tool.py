from uuid import UUID
from sqlalchemy.orm import Session

from ada_backend.database.models import (
    Component,
    ComponentParameterDefinition,
    UIComponent,
    UIComponentProperties,
    ParameterType,
)
from ada_backend.database.component_definition_seeding import (
    upsert_component_categories,
    upsert_component_versions,
    upsert_components,
    upsert_components_parameter_definitions,
    upsert_release_stage_to_current_version_mapping,
)
from ada_backend.database.seed.seed_categories import CATEGORY_UUIDS
from ada_backend.database.seed.utils import COMPONENT_UUIDS, COMPONENT_VERSION_UUIDS
from ada_backend.database.seed.seed_tool_description import TOOL_DESCRIPTION_UUIDS
from ada_backend.database import models as db


def seed_mcp_client_components(session: Session):
    mcp_component = Component(
        id=COMPONENT_UUIDS["mcp_client_tool"],
        name="MCP Client Tool",
        is_agent=False,
        function_callable=True,
        can_use_function_calling=False,
        icon="tabler-api-app",
    )
    upsert_components(session, [mcp_component])

    mcp_component_version = db.ComponentVersion(
        id=COMPONENT_VERSION_UUIDS["mcp_client_tool"],
        component_id=COMPONENT_UUIDS["mcp_client_tool"],
        version_tag="0.0.1",
        release_stage=db.ReleaseStage.PUBLIC,
        description="Connect to an MCP server and expose its tools to the agent.",
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["mcp_client_tool_description"],
    )
    upsert_component_versions(session, [mcp_component_version])

    mcp_parameter_definitions = [
        ComponentParameterDefinition(
            id=UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890"),
            component_version_id=mcp_component_version.id,
            name="server_command",
            type=ParameterType.STRING,
            nullable=False,
            ui_component=UIComponent.TEXTFIELD,
            ui_component_properties=UIComponentProperties(
                label="Server Command",
                placeholder="uvx",
                description="The command to run the MCP server (e.g. 'uvx', 'npx', 'python', 'docker').",
            ).model_dump(exclude_unset=True, exclude_none=True),
        ),
        ComponentParameterDefinition(
            id=UUID("b2c3d4e5-f6a7-8901-bcde-f12345678901"),
            component_version_id=mcp_component_version.id,
            name="server_args",
            type=ParameterType.STRING,
            nullable=False,
            ui_component=UIComponent.TEXTAREA,
            ui_component_properties=UIComponentProperties(
                label="Server Arguments",
                placeholder='["mcp-server-sqlite", "--db-path", "test.db"]',
                description="List of arguments for the server command (JSON list).",
            ).model_dump(exclude_unset=True, exclude_none=True),
        ),
        ComponentParameterDefinition(
            id=UUID("c3d4e5f6-a7b8-9012-cdef-123456789012"),
            component_version_id=mcp_component_version.id,
            name="server_env",
            type=ParameterType.STRING,
            nullable=True,
            ui_component=UIComponent.TEXTAREA,
            ui_component_properties=UIComponentProperties(
                label="Environment Variables",
                placeholder='{"API_KEY": "secret"}',
                description="Environment variables for the server process (JSON object).",
            ).model_dump(exclude_unset=True, exclude_none=True),
        ),
    ]

    upsert_components_parameter_definitions(session, mcp_parameter_definitions)
    upsert_component_categories(
        session=session,
        component_id=mcp_component.id,
        category_ids=[CATEGORY_UUIDS["action"]],
    )

    # Create release stage mapping
    upsert_release_stage_to_current_version_mapping(
        session=session,
        component_id=mcp_component_version.component_id,
        release_stage=mcp_component_version.release_stage,
        component_version_id=mcp_component_version.id,
    )
