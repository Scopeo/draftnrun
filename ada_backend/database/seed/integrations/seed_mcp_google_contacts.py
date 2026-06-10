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


def seed_mcp_google_contacts_components(session: Session):
    google_contacts_neverdrop_mcp_tool_component = Component(
        id=COMPONENT_UUIDS["google_contacts_neverdrop_mcp_tool"],
        name="Google Contacts Neverdrop",
        is_agent=True,
        function_callable=True,
        can_use_function_calling=False,
        icon="logos:google-icon",
    )
    upsert_components(session, [google_contacts_neverdrop_mcp_tool_component])

    google_contacts_neverdrop_mcp_tool_version = db.ComponentVersion(
        id=COMPONENT_VERSION_UUIDS["google_contacts_neverdrop_mcp_tool"],
        component_id=COMPONENT_UUIDS["google_contacts_neverdrop_mcp_tool"],
        version_tag="0.0.1",
        release_stage=db.ReleaseStage.INTERNAL,
        description=(
            "Connect to Google Contacts Neverdrop via MCP to list, search, and get contacts and Other "
            "contacts, with sync-token support for incremental change feeds."
        ),
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["google_contacts_neverdrop_mcp_tool_description"],
    )
    upsert_component_versions(session, [google_contacts_neverdrop_mcp_tool_version])

    google_contacts_neverdrop_mcp_tool_parameter_definitions = [
        ComponentParameterDefinition(
            id=UUID("56bde7d5-1c5f-4a69-b232-5055abcb974e"),
            component_version_id=google_contacts_neverdrop_mcp_tool_version.id,
            name="oauth_connection_id",
            type=ParameterType.STRING,
            nullable=True,
            display_order=None,
            parameter_order_within_group=0,
            ui_component=UIComponent.OAUTH_CONNECTION,
            ui_component_properties=UIComponentProperties(
                label="Google Contacts Neverdrop Connection",
                description="Select your authorized Google Contacts Neverdrop account connection",
                provider=OAuthProvider.GOOGLE_CONTACT_NEVERDROP.value,
                icon="logos:google-icon",
            ).model_dump(exclude_unset=True, exclude_none=True),
        )
    ]

    upsert_components_parameter_definitions(session, google_contacts_neverdrop_mcp_tool_parameter_definitions)

    upsert_release_stage_to_current_version_mapping(
        session=session,
        component_id=google_contacts_neverdrop_mcp_tool_version.component_id,
        release_stage=google_contacts_neverdrop_mcp_tool_version.release_stage,
        component_version_id=google_contacts_neverdrop_mcp_tool_version.id,
    )

    upsert_component_categories(
        session=session,
        component_id=google_contacts_neverdrop_mcp_tool_component.id,
        category_ids=[CATEGORY_UUIDS["integrations"], CATEGORY_UUIDS["information_retrieval"]],
    )
