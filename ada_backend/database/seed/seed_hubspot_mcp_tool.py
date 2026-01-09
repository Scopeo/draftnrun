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


def seed_hubspot_mcp_tool_components(session: Session):
    hubspot_mcp_component = Component(
        id=COMPONENT_UUIDS["hubspot_mcp_tool"],
        name="HubSpot MCP",
        is_agent=False,
        function_callable=True,
        can_use_function_calling=False,
        icon="tabler-brand-hubspot",
    )
    upsert_components(session, [hubspot_mcp_component])

    hubspot_mcp_component_version = db.ComponentVersion(
        id=COMPONENT_VERSION_UUIDS["hubspot_mcp_tool"],
        component_id=COMPONENT_UUIDS["hubspot_mcp_tool"],
        version_tag="0.0.1",
        release_stage=db.ReleaseStage.INTERNAL,
        description="Connect to HubSpot CRM via MCP server. Requires HUBSPOT_MCP_ACCESS_TOKEN in credentials.env (obtain via scripts/get_hubspot_oauth_token.py).",
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["default_tool_description"],
    )
    upsert_component_versions(session, [hubspot_mcp_component_version])

    # No parameters - tokens come from environment variables only
    parameter_definitions = []
    upsert_components_parameter_definitions(session, parameter_definitions)
    upsert_component_categories(
        session=session,
        component_id=hubspot_mcp_component.id,
        category_ids=[CATEGORY_UUIDS["action"], CATEGORY_UUIDS["query"]],
    )
    upsert_release_stage_to_current_version_mapping(
        session=session,
        component_id=hubspot_mcp_component_version.component_id,
        release_stage=hubspot_mcp_component_version.release_stage,
        component_version_id=hubspot_mcp_component_version.id,
    )
