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
    SelectOption,
    UIComponent,
    UIComponentProperties,
)
from ada_backend.database.seed.seed_categories import CATEGORY_UUIDS
from ada_backend.database.seed.seed_tool_description import TOOL_DESCRIPTION_UUIDS
from ada_backend.database.seed.utils import COMPONENT_UUIDS, COMPONENT_VERSION_UUIDS
from engine.components.tools.notion_mcp_tool import NOTION_DEFAULT_TOOL_NAMES
from engine.integrations.providers import OAuthProvider


def seed_mcp_notion_neverdrop_components(session: Session):
    component = Component(
        id=COMPONENT_UUIDS["notion_neverdrop_mcp_tool"],
        name="Notion NeverDrop MCP Tool",
        is_agent=True,
        function_callable=True,
        can_use_function_calling=False,
        icon="simple-icons:notion",
    )
    upsert_components(session, [component])

    version = db.ComponentVersion(
        id=COMPONENT_VERSION_UUIDS["notion_neverdrop_mcp_tool"],
        component_id=COMPONENT_UUIDS["notion_neverdrop_mcp_tool"],
        version_tag="0.0.1",
        release_stage=db.ReleaseStage.INTERNAL,
        description=(
            "Connect to Notion via MCP to access database and page tools "
            "(search, create/query databases, create/update pages, manage blocks, smart upserts)."
        ),
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["notion_neverdrop_mcp_tool_description"],
    )
    upsert_component_versions(session, [version])

    parameter_definitions = [
        ComponentParameterDefinition(
            id=UUID("abcca3da-0719-4ed2-8107-0515e990a367"),
            component_version_id=version.id,
            name="oauth_connection_id",
            type=ParameterType.STRING,
            nullable=True,
            display_order=None,
            parameter_order_within_group=0,
            ui_component=UIComponent.OAUTH_CONNECTION,
            ui_component_properties=UIComponentProperties(
                label="Notion NeverDrop Connection",
                description="Select your authorized Notion account connection",
                provider=OAuthProvider.NOTION_NEVERDROP.value,
                icon="simple-icons:notion",
            ).model_dump(exclude_unset=True, exclude_none=True),
        ),
        ComponentParameterDefinition(
            id=UUID("b1f032a8-b137-40da-8a62-5072b6637c16"),
            component_version_id=version.id,
            name="allowed_tools",
            type=ParameterType.JSON,
            nullable=True,
            display_order=None,
            parameter_order_within_group=1,
            ui_component=UIComponent.MULTISELECT,
            ui_component_properties=UIComponentProperties(
                label="Allowed Notion tools",
                description="Select the Notion tools that this component instance can call.",
                options=[SelectOption(value=name, label=name) for name in NOTION_DEFAULT_TOOL_NAMES],
            ).model_dump(exclude_unset=True, exclude_none=True),
        ),
    ]

    upsert_components_parameter_definitions(session, parameter_definitions)

    upsert_release_stage_to_current_version_mapping(
        session=session,
        component_id=version.component_id,
        release_stage=version.release_stage,
        component_version_id=version.id,
    )

    upsert_component_categories(
        session=session,
        component_id=component.id,
        category_ids=[CATEGORY_UUIDS["integrations"], CATEGORY_UUIDS["information_retrieval"]],
    )
