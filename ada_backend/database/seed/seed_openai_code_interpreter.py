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
    build_web_service_config_definitions,
)
from ada_backend.services.registry import COMPLETION_MODEL_IN_DB


def seed_openai_code_interpreter_components(session: Session):
    openai_code_interpreter_agent = db.Component(
        id=COMPONENT_UUIDS["openai_code_interpreter_agent"],
        name="OpenAI Code Interpreter",
        description="Execute Python code using OpenAI's code interpreter",
        is_agent=False,
        function_callable=True,
        release_stage=db.ReleaseStage.BETA,
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["default_openai_code_interpreter_tool_description"],
    )
    upsert_components(
        session=session,
        components=[
            openai_code_interpreter_agent,
        ],
    )
    upsert_components_parameter_definitions(
        session=session,
        component_parameter_definitions=[
            # OpenAI Code Interpreter Agent
            *build_web_service_config_definitions(
                component_id=openai_code_interpreter_agent.id,
                params_to_seed=[
                    ParameterLLMConfig(
                        param_name=COMPLETION_MODEL_IN_DB,
                        param_id=UUID("429f22ec-0382-4fcf-963f-3281e68e6224"),
                    ),
                    ParameterLLMConfig(
                        param_name="api_key",
                        param_id=UUID("a1e57044-3762-4791-bc4d-32fcfb9d87cf"),
                    ),
                ],
            ),
        ],
    )