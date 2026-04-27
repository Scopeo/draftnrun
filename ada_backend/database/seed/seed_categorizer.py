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
from ada_backend.database.seed.constants import (
    REASONING_IN_DB,
    TEMPERATURE_IN_DB,
    VERBOSITY_IN_DB,
)
from ada_backend.database.seed.seed_categories import CATEGORY_UUIDS
from ada_backend.database.seed.utils import (
    COMPONENT_UUIDS,
    COMPONENT_VERSION_UUIDS,
    ParameterLLMConfig,
    build_completion_service_config_definitions,
    build_components_parameters_assignments_to_parameter_groups,
    build_parameters_group,
    build_parameters_group_definitions,
)
from engine.components.categorizer import DEFAULT_CATEGORIZER_TOOL_DESCRIPTION

CATEGORIZER_PARAMETER_IDS = {
    "categories": UUID("732e8650-793a-4fa1-94a9-c8d0143a5592"),
    "additional_context": UUID("e9c90431-c7f0-4e45-8cc1-a0d0158580e7"),
    TEMPERATURE_IN_DB: UUID("0e3056f2-25b9-4a85-8cd5-d658180dc6eb"),
    VERBOSITY_IN_DB: UUID("bf687ed1-f576-4a8b-88aa-ad5c9c4b8ad4"),
    REASONING_IN_DB: UUID("cdbf4980-b611-44a1-9e59-11636ad7a585"),
    "api_key": UUID("e75801be-df57-40b5-a077-2c8b0a65c80e"),
}

CATEGORIZER_PARAMETER_GROUP_UUIDS = {
    "advanced_llm_parameters": UUID("dc7c98b3-db0e-401b-a5a8-57af085c133d"),
}

CATEGORIZER_TOOL_DESCRIPTION_ID = UUID("8f9d4c3e-7a2b-4e1d-9c8f-5b6a3d2e1f0a")


def seed_categorizer_components(session: Session):
    categorizer_tool_description = db.ToolDescription(
        id=CATEGORIZER_TOOL_DESCRIPTION_ID,
        **DEFAULT_CATEGORIZER_TOOL_DESCRIPTION.model_dump(),
    )
    session.merge(categorizer_tool_description)
    session.flush()

    categorizer = db.Component(
        id=COMPONENT_UUIDS["categorizer"],
        name="Categorizer",
        is_agent=True,
        function_callable=True,
        icon="tabler-category",
    )
    upsert_components(
        session=session,
        components=[
            categorizer,
        ],
    )
    categorizer_version = db.ComponentVersion(
        id=COMPONENT_VERSION_UUIDS["categorizer"],
        component_id=COMPONENT_UUIDS["categorizer"],
        version_tag="0.0.1",
        release_stage=db.ReleaseStage.PUBLIC,
        description="A component that categorizes content into user-defined categories using AI.",
        default_tool_description_id=CATEGORIZER_TOOL_DESCRIPTION_ID,
    )
    upsert_component_versions(
        session=session,
        component_versions=[categorizer_version],
    )
    upsert_components_parameter_definitions(
        session=session,
        component_parameter_definitions=[
            *build_completion_service_config_definitions(
                component_version_id=categorizer_version.id,
                params_to_seed=[
                    ParameterLLMConfig(
                        param_name=TEMPERATURE_IN_DB,
                        param_id=CATEGORIZER_PARAMETER_IDS[TEMPERATURE_IN_DB],
                    ),
                    ParameterLLMConfig(
                        param_name=VERBOSITY_IN_DB,
                        param_id=CATEGORIZER_PARAMETER_IDS[VERBOSITY_IN_DB],
                    ),
                    ParameterLLMConfig(
                        param_name=REASONING_IN_DB,
                        param_id=CATEGORIZER_PARAMETER_IDS[REASONING_IN_DB],
                    ),
                    ParameterLLMConfig(
                        param_name="api_key",
                        param_id=CATEGORIZER_PARAMETER_IDS["api_key"],
                    ),
                ],
            ),
        ],
    )

    upsert_release_stage_to_current_version_mapping(
        session=session,
        component_id=categorizer_version.component_id,
        release_stage=categorizer_version.release_stage,
        component_version_id=categorizer_version.id,
    )

    upsert_component_categories(
        session=session,
        component_id=categorizer.id,
        category_ids=[CATEGORY_UUIDS["ai"]],
    )


def seed_categorizer_parameter_groups(session: Session):

    parameter_groups = [
        db.ParameterGroup(
            id=CATEGORIZER_PARAMETER_GROUP_UUIDS["advanced_llm_parameters"], name="Advanced LLM Parameters"
        ),
    ]
    build_parameters_group(session, parameter_groups)

    component_parameter_groups = [
        db.ComponentParameterGroup(
            component_version_id=COMPONENT_VERSION_UUIDS["categorizer"],
            parameter_group_id=CATEGORIZER_PARAMETER_GROUP_UUIDS["advanced_llm_parameters"],
            group_order_within_component=1,
        ),
    ]
    build_parameters_group_definitions(session, component_parameter_groups)

    parameter_group_assignments = {
        # Advanced LLM Parameters Group
        CATEGORIZER_PARAMETER_IDS[TEMPERATURE_IN_DB]: {
            "parameter_group_id": CATEGORIZER_PARAMETER_GROUP_UUIDS["advanced_llm_parameters"],
            "parameter_order_within_group": 1,
        },
        CATEGORIZER_PARAMETER_IDS[VERBOSITY_IN_DB]: {
            "parameter_group_id": CATEGORIZER_PARAMETER_GROUP_UUIDS["advanced_llm_parameters"],
            "parameter_order_within_group": 2,
        },
        CATEGORIZER_PARAMETER_IDS[REASONING_IN_DB]: {
            "parameter_group_id": CATEGORIZER_PARAMETER_GROUP_UUIDS["advanced_llm_parameters"],
            "parameter_order_within_group": 3,
        },
    }
    build_components_parameters_assignments_to_parameter_groups(session, parameter_group_assignments)
