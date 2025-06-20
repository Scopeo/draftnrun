from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.models import ParameterType
from ada_backend.database.component_definition_seeding import (
    upsert_components,
    upsert_components_parameter_child_relationships,
    upsert_components_parameter_definitions,
)
from ada_backend.database.seed.seed_tool_description import TOOL_DESCRIPTION_UUIDS
from ada_backend.database.seed.utils import (
    COMPONENT_UUIDS,
    ParameterLLMConfig,
    build_completion_service_config_definitions,
)
from ada_backend.services.registry import COMPLETION_MODEL_IN_DB


def seed_tavily_components(session: Session):
    # TODO fix is_agent=True
    tavily_agent = db.Component(
        id=COMPONENT_UUIDS["tavily_agent"],
        name="Internet Search with Tavily",
        description="Performs internet search using Tavily",
        is_agent=False,
        function_callable=False,
        release_stage=db.ReleaseStage.INTERNAL,
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["tavily_tool_description"],
    )
    upsert_components(
        session=session,
        components=[
            tavily_agent,
        ],
    )
    # Tavily
    tavily_synthesizer_param = db.ComponentParameterDefinition(
        id=UUID("24e16437-87d8-4b65-b2f8-63711ed97b8f"),
        component_id=tavily_agent.id,
        name="synthesizer",
        type=ParameterType.COMPONENT,
        nullable=True,
    )
    upsert_components_parameter_definitions(
        session=session,
        component_parameter_definitions=[tavily_synthesizer_param],
    )
    upsert_components_parameter_child_relationships(
        session=session,
        component_parameter_child_relationships=[
            db.ComponentParameterChildRelationship(
                id=UUID("5592a748-efc1-4dd0-9600-d4a41e9bba94"),
                component_parameter_definition_id=tavily_synthesizer_param.id,
                child_component_id=COMPONENT_UUIDS["synthesizer"],
            ),
        ],
    )
    upsert_components_parameter_definitions(
        session=session,
        component_parameter_definitions=[
            # Tavily Agent
            *build_completion_service_config_definitions(
                component_id=tavily_agent.id,
                params_to_seed=[
                    ParameterLLMConfig(
                        param_name=COMPLETION_MODEL_IN_DB,
                        param_id=UUID("2a2780b2-f361-4e78-a370-02eb08b4b68e"),
                    ),
                    ParameterLLMConfig(
                        param_name="api_key",
                        param_id=UUID("59ba9e31-10f4-47f8-9cce-6bffe46587ee"),
                    ),
                ],
            ),
        ],
    )
