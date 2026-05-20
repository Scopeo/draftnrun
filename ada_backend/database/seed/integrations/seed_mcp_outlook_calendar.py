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
from engine.integrations.providers import OAuthProvider


def seed_mcp_outlook_calendar_components(session: Session):
    outlook_calendar_mcp_tool_component = Component(
        id=COMPONENT_UUIDS["outlook_calendar_mcp_tool"],
        name="Outlook Calendar",
        is_agent=True,
        function_callable=True,
        can_use_function_calling=False,
        icon="vscode-icons:file-type-outlook",
    )

    upsert_components(session, [outlook_calendar_mcp_tool_component])

    outlook_calendar_mcp_tool_version = db.ComponentVersion(
        id=COMPONENT_VERSION_UUIDS["outlook_calendar_mcp_tool"],
        component_id=COMPONENT_UUIDS["outlook_calendar_mcp_tool"],
        version_tag="0.0.1",
        release_stage=db.ReleaseStage.INTERNAL,
        description="Connect to Outlook Calendar via MCP to list, create, update, and delete events.",
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["outlook_calendar_mcp_tool_description"],
    )

    upsert_component_versions(session, [outlook_calendar_mcp_tool_version])

    parameter_definitions = [
        ComponentParameterDefinition(
            id=UUID("0f8ec94f-3ac9-4b96-994a-1c9a0d9865f0"),
            component_version_id=outlook_calendar_mcp_tool_version.id,
            name="oauth_connection_id",
            type=ParameterType.STRING,
            nullable=True,
            display_order=None,
            parameter_order_within_group=0,
            ui_component=UIComponent.OAUTH_CONNECTION,
            ui_component_properties=UIComponentProperties(
                label="Outlook Calendar Connection",
                description="Select your authorized Outlook Calendar account connection",
                provider=OAuthProvider.OUTLOOK_CALENDAR.value,
                icon="vscode-icons:file-type-outlook",
            ).model_dump(exclude_unset=True, exclude_none=True),
        )
    ]

    upsert_components_parameter_definitions(session, parameter_definitions)

    upsert_release_stage_to_current_version_mapping(
        session=session,
        component_id=outlook_calendar_mcp_tool_version.component_id,
        release_stage=outlook_calendar_mcp_tool_version.release_stage,
        component_version_id=outlook_calendar_mcp_tool_version.id,
    )

    upsert_component_categories(
        session=session,
        component_id=outlook_calendar_mcp_tool_component.id,
        category_ids=[CATEGORY_UUIDS["integrations"], CATEGORY_UUIDS["information_retrieval"]],
    )
