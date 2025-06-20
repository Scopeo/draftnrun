from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database import models as db
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


def seed_web_search_components(session: Session):
    web_search_openai_agent = db.Component(
        id=COMPONENT_UUIDS["web_search_openai_agent"],
        name="Internet Search with OpenAI",
        description="Performs internet search using OpenAI",
        is_agent=False,
        function_callable=True,
        release_stage=db.ReleaseStage.BETA,
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["default_web_search_openai_tool_description"],
    )
    upsert_components(
        session=session,
        components=[
            web_search_openai_agent,
        ],
    )
    upsert_components_parameter_definitions(
        session=session,
        component_parameter_definitions=[
            # Web Search OpenAI Agent
            *build_completion_service_config_definitions(
                component_id=web_search_openai_agent.id,
                params_to_seed=[
                    ParameterLLMConfig(
                        param_name="web_search_model_name",
                        param_id=UUID("329f22ec-0382-4fcf-963f-3281e68e6223"),
                    ),
                    ParameterLLMConfig(
                        param_name="api_key",
                        param_id=UUID("f1e57044-3762-4791-bc4d-32fcfb9d87cf"),
                    ),
                ],
            ),
        ],
    )
