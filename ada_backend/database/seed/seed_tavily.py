from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.models import ParameterType
from ada_backend.database.component_definition_seeding import (
    upsert_component_versions,
    upsert_components,
    upsert_components_parameter_child_relationships,
    upsert_components_parameter_definitions,
    upsert_release_stage_to_current_version_mapping,
)
from ada_backend.database.seed.seed_tool_description import TOOL_DESCRIPTION_UUIDS
from ada_backend.database.seed.utils import (
    COMPONENT_UUIDS,
    COMPONENT_VERSION_UUIDS,
    ParameterLLMConfig,
    build_completion_service_config_definitions,
)
from ada_backend.database.seed.constants import COMPLETION_MODEL_IN_DB


def seed_tavily_components(session: Session):
    # TODO fix is_agent=True
    tavily_agent = db.Component(
        id=COMPONENT_UUIDS["tavily_agent"],
        name="Internet Search with Tavily",
        is_agent=False,
        function_callable=False,
    )
    upsert_components(
        session=session,
        components=[
            tavily_agent,
        ],
    )
    tavily_agent_version = db.ComponentVersion(
        id=COMPONENT_VERSION_UUIDS["tavily_agent"],
        component_id=COMPONENT_UUIDS["tavily_agent"],
        version_tag="v0.1.0",
        release_stage=db.ReleaseStage.INTERNAL,
        description="Agent that uses Tavily to perform internet searches and answer questions based on the results.",
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["tavily_tool_description"],
    )
    upsert_component_versions(
        session=session,
        component_versions=[tavily_agent_version],
    )
    # Tavily
    tavily_synthesizer_param = db.ComponentParameterDefinition(
        id=UUID("24e16437-87d8-4b65-b2f8-63711ed97b8f"),
        component_version_id=tavily_agent_version.id,
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
                child_component_version_id=COMPONENT_VERSION_UUIDS["synthesizer"],
            ),
        ],
    )
    upsert_components_parameter_definitions(
        session=session,
        component_parameter_definitions=[
            # Tavily Agent
            *build_completion_service_config_definitions(
                session=session,
                component_version_id=tavily_agent_version.id,
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

    upsert_release_stage_to_current_version_mapping(
        session=session,
        component_id=tavily_agent_version.component_id,
        release_stage=tavily_agent_version.release_stage,
        component_version_id=tavily_agent_version.id,
    )
