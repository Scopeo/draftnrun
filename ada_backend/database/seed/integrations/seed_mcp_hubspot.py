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


def seed_mcp_hubspot_components(session: Session):
    hubspot_mcp_tool_component = Component(
        id=COMPONENT_UUIDS["hubspot_mcp_tool"],
        name="HubSpot MCP Tool",
        is_agent=False,
        function_callable=True,
        can_use_function_calling=False,
        icon="logos:hubspot",
    )
    upsert_components(session, [hubspot_mcp_tool_component])

    hubspot_mcp_tool_version = db.ComponentVersion(
        id=COMPONENT_VERSION_UUIDS["hubspot_mcp_tool"],
        component_id=COMPONENT_UUIDS["hubspot_mcp_tool"],
        version_tag="0.0.1",
        release_stage=db.ReleaseStage.INTERNAL,
        description="Connect to HubSpot via MCP to access CRM tools (contacts, deals, companies, tickets, etc.).",
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["hubspot_mcp_tool_description"],
    )
    upsert_component_versions(session, [hubspot_mcp_tool_version])

    hubspot_mcp_tool_parameter_definitions = [
        ComponentParameterDefinition(
            id=UUID("8a7b6c5d-4e3f-2a1b-0c9d-8e7f6a5b4c3d"),
            component_version_id=hubspot_mcp_tool_version.id,
            name="oauth_connection_id",
            type=ParameterType.STRING,
            nullable=False,
            order=None,
            parameter_order_within_group=0,
            ui_component=UIComponent.OAUTH_CONNECTION,
            ui_component_properties=UIComponentProperties(
                label="HubSpot Connection",
                description="Select your authorized HubSpot account connection",
                provider=OAuthProvider.HUBSPOT.value,
                icon="logos:hubspot",
            ).model_dump(exclude_unset=True, exclude_none=True),
        )
    ]

    upsert_components_parameter_definitions(session, hubspot_mcp_tool_parameter_definitions)

    upsert_release_stage_to_current_version_mapping(
        session=session,
        component_id=hubspot_mcp_tool_version.component_id,
        release_stage=hubspot_mcp_tool_version.release_stage,
        component_version_id=hubspot_mcp_tool_version.id,
    )

    upsert_component_categories(
        session=session,
        component_id=hubspot_mcp_tool_component.id,
        category_ids=[CATEGORY_UUIDS["integrations"], CATEGORY_UUIDS["information_retrieval"]],
    )
