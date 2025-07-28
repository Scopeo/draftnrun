from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.models import (
    ParameterType,
    UIComponent,
    UIComponentProperties,
)
from ada_backend.database.component_definition_seeding import (
    upsert_components,
    upsert_components_parameter_definitions,
)
from ada_backend.database.seed.seed_tool_description import TOOL_DESCRIPTION_UUIDS
from ada_backend.database.seed.utils import (
    COMPONENT_UUIDS,
    ParameterLLMConfig,
    build_completion_service_config_definitions,
)
from ada_backend.services.registry import COMPLETION_MODEL_IN_DB


def seed_linkup_tool_components(session: Session):
    linkup_tool = db.Component(
        id=COMPONENT_UUIDS["linkup_search_tool"],
        name="Linkup Search Tool",
        description="Linkup search tool for real-time web search and data connection",
        is_agent=False,
        function_callable=True,
        release_stage=db.ReleaseStage.PUBLIC,
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["linkup_search_tool_description"],
    )
    
    upsert_components(
        session=session,
        components=[
            linkup_tool,
        ],
    )
    
    # Linkup tool parameter definitions
    linkup_tool_parameter_definitions = [
        db.ComponentParameterDefinition(
            id=UUID("f4e56789-abcd-ef01-2345-6789abcdef01"),
            component_id=linkup_tool.id,
            name="trace_manager",
            type=ParameterType.COMPONENT,
            nullable=False,
        ),
        db.ComponentParameterDefinition(
            id=UUID("f4e56789-abcd-ef01-2345-6789abcdef02"),
            component_id=linkup_tool.id,
            name="component_attributes",
            type=ParameterType.COMPONENT,
            nullable=False,
        ),
        db.ComponentParameterDefinition(
            id=UUID("f4e56789-abcd-ef01-2345-6789abcdef03"),
            component_id=linkup_tool.id,
            name="tool_description",
            type=ParameterType.COMPONENT,
            nullable=True,
        ),
        db.ComponentParameterDefinition(
            id=UUID("f4e56789-abcd-ef01-2345-6789abcdef04"),
            component_id=linkup_tool.id,
            name="linkup_api_key",
            type=ParameterType.STRING,
            nullable=True,
            default_value="${LINKUP_API_KEY}",
            ui_component=UIComponent.INPUT,
            ui_component_properties=UIComponentProperties(
                label="Linkup API Key",
                description="API key for Linkup search service. If not provided, will use global LINKUP_API_KEY from settings.",
                placeholder="Enter your Linkup API key",
            ),
        ),
        db.ComponentParameterDefinition(
            id=UUID("f4e56789-abcd-ef01-2345-6789abcdef05"),
            component_id=linkup_tool.id,
            name="base_url",
            type=ParameterType.STRING,
            nullable=True,
            default_value="https://api.linkup.so/v1",
            ui_component=UIComponent.INPUT,
            ui_component_properties=UIComponentProperties(
                label="Base URL",
                description="Base URL for Linkup API (default: https://api.linkup.so/v1)",
                placeholder="https://api.linkup.so/v1",
            ),
        ),
        db.ComponentParameterDefinition(
            id=UUID("f4e56789-abcd-ef01-2345-6789abcdef06"),
            component_id=linkup_tool.id,
            name="timeout",
            type=ParameterType.INTEGER,
            nullable=True,
            default_value="30",
            ui_component=UIComponent.INPUT,
            ui_component_properties=UIComponentProperties(
                label="Timeout (seconds)",
                description="Request timeout in seconds (default: 30)",
                placeholder="30",
            ),
        ),
    ]
    
    upsert_components_parameter_definitions(
        session=session,
        component_parameter_definitions=linkup_tool_parameter_definitions,
    )