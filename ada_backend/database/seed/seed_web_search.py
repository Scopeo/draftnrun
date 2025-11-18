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
from ada_backend.database.seed.seed_categories import CATEGORY_UUIDS
from ada_backend.database.seed.seed_tool_description import TOOL_DESCRIPTION_UUIDS
from ada_backend.database.seed.utils import (
    COMPONENT_UUIDS,
    COMPONENT_VERSION_UUIDS,
    ParameterLLMConfig,
    build_web_service_config_definitions,
)
from ada_backend.database.seed.constants import (
    COMPLETION_MODEL_IN_DB,
)
from ada_backend.database.models import ParameterType, UIComponent, UIComponentProperties


def seed_web_search_components(session: Session):
    web_search_openai_agent = db.Component(
        id=COMPONENT_UUIDS["web_search_openai_agent"],
        name="Internet Search (OpenAI)",
        is_agent=False,
        function_callable=True,
        icon="tabler-world-search",
    )
    upsert_components(
        session=session,
        components=[
            web_search_openai_agent,
        ],
    )
    web_search_openai_agent_version = db.ComponentVersion(
        id=COMPONENT_VERSION_UUIDS["web_search_openai_agent_v2"],
        component_id=COMPONENT_UUIDS["web_search_openai_agent"],
        version_tag="0.0.2",
        release_stage=db.ReleaseStage.PUBLIC,
        description="Agent that uses OpenAI to perform internet searches and answer questions based on the results.",
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["default_web_search_openai_tool_description"],
    )
    upsert_component_versions(
        session=session,
        component_versions=[web_search_openai_agent_version],
    )
    upsert_components_parameter_definitions(
        session=session,
        component_parameter_definitions=[
            # Web Search OpenAI Agent
            *build_web_service_config_definitions(
                component_version_id=web_search_openai_agent_version.id,
                params_to_seed=[
                    ParameterLLMConfig(
                        param_name=COMPLETION_MODEL_IN_DB,
                        param_id=UUID("329f22ec-0382-4fcf-963f-3281e68e6222"),
                    ),
                    ParameterLLMConfig(
                        param_name="api_key",
                        param_id=UUID("f1e57044-3762-4791-bc4d-32fcfb9d87ce"),
                    ),
                ],
            ),
            db.ComponentParameterDefinition(
                id=UUID("b2c3d4e5-f6a7-8901-abba-f12347653901"),
                component_version_id=web_search_openai_agent_version.id,
                name="allowed_domains",
                type=ParameterType.STRING,
                nullable=True,
                default=None,
                ui_component=UIComponent.TEXTAREA,
                ui_component_properties=UIComponentProperties(
                    label="Allowed Domains",
                    description="Restrict web search results to specific domains.",
                    placeholder='["wikipedia.org", "example.com"]',
                ).model_dump(exclude_unset=True, exclude_none=True),
            ),
        ],
    )
    upsert_component_categories(
        session=session,
        component_id=web_search_openai_agent.id,
        category_ids=[CATEGORY_UUIDS["query"]],
    )

    # Create release stage mapping
    upsert_release_stage_to_current_version_mapping(
        session=session,
        component_id=web_search_openai_agent_version.component_id,
        release_stage=web_search_openai_agent_version.release_stage,
        component_version_id=web_search_openai_agent_version.id,
    )
