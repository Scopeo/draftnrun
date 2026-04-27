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
from ada_backend.database.seed.seed_tool_description import TOOL_DESCRIPTION_UUIDS
from ada_backend.database.seed.utils import (
    COMPONENT_UUIDS,
    COMPONENT_VERSION_UUIDS,
    ParameterLLMConfig,
    build_completion_service_config_definitions,
    build_components_parameters_assignments_to_parameter_groups,
    build_parameters_group,
    build_parameters_group_definitions,
)

SCORER_PARAMETER_IDS = {
    TEMPERATURE_IN_DB: UUID("0e3056f2-25b9-4a85-8cd5-d658180dc6ec"),
    VERBOSITY_IN_DB: UUID("bf687ed1-f576-4a8b-88aa-ad5c9c4b8ad5"),
    REASONING_IN_DB: UUID("cdbf4980-b611-44a1-9e59-11636ad7a586"),
    "api_key": UUID("e75801be-df57-40b5-a077-2c8b0a65c80f"),
}

SCORER_PARAMETER_GROUP_UUIDS = {
    "advanced_llm_parameters": UUID("dc7c98b3-db0e-401b-a5a8-57af085c133e"),
}


def seed_scorer_components(session: Session):
    scorer = db.Component(
        id=COMPONENT_UUIDS["scorer"],
        name="Scorer",
        is_agent=True,
        function_callable=True,
        icon="tabler-gauge",
    )
    upsert_components(
        session=session,
        components=[
            scorer,
        ],
    )
    scorer_version = db.ComponentVersion(
        id=COMPONENT_VERSION_UUIDS["scorer"],
        component_id=COMPONENT_UUIDS["scorer"],
        version_tag="0.0.1",
        release_stage=db.ReleaseStage.BETA,
        description=(
            "Assign a numerical score from 0 to 100, based on predefined criteria, "
            "to quantitatively assess the quality of a given entity."
        ),
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["scorer_tool_description"],
    )
    upsert_component_versions(
        session=session,
        component_versions=[scorer_version],
    )
    upsert_components_parameter_definitions(
        session=session,
        component_parameter_definitions=[
            *build_completion_service_config_definitions(
                component_version_id=scorer_version.id,
                params_to_seed=[
                    ParameterLLMConfig(
                        param_name=TEMPERATURE_IN_DB,
                        param_id=SCORER_PARAMETER_IDS[TEMPERATURE_IN_DB],
                    ),
                    ParameterLLMConfig(
                        param_name=VERBOSITY_IN_DB,
                        param_id=SCORER_PARAMETER_IDS[VERBOSITY_IN_DB],
                    ),
                    ParameterLLMConfig(
                        param_name=REASONING_IN_DB,
                        param_id=SCORER_PARAMETER_IDS[REASONING_IN_DB],
                    ),
                    ParameterLLMConfig(
                        param_name="api_key",
                        param_id=SCORER_PARAMETER_IDS["api_key"],
                    ),
                ],
            ),
        ],
    )

    upsert_release_stage_to_current_version_mapping(
        session=session,
        component_id=scorer_version.component_id,
        release_stage=scorer_version.release_stage,
        component_version_id=scorer_version.id,
    )

    upsert_component_categories(
        session=session,
        component_id=scorer.id,
        category_ids=[CATEGORY_UUIDS["ai"]],
    )


def seed_scorer_parameter_groups(session: Session):
    parameter_groups = [
        db.ParameterGroup(id=SCORER_PARAMETER_GROUP_UUIDS["advanced_llm_parameters"], name="Advanced LLM Parameters"),
    ]
    build_parameters_group(session, parameter_groups)

    component_parameter_groups = [
        db.ComponentParameterGroup(
            component_version_id=COMPONENT_VERSION_UUIDS["scorer"],
            parameter_group_id=SCORER_PARAMETER_GROUP_UUIDS["advanced_llm_parameters"],
            group_order_within_component=1,
        ),
    ]
    build_parameters_group_definitions(session, component_parameter_groups)

    parameter_group_assignments = {
        SCORER_PARAMETER_IDS[TEMPERATURE_IN_DB]: {
            "parameter_group_id": SCORER_PARAMETER_GROUP_UUIDS["advanced_llm_parameters"],
            "parameter_order_within_group": 1,
        },
        SCORER_PARAMETER_IDS[VERBOSITY_IN_DB]: {
            "parameter_group_id": SCORER_PARAMETER_GROUP_UUIDS["advanced_llm_parameters"],
            "parameter_order_within_group": 2,
        },
        SCORER_PARAMETER_IDS[REASONING_IN_DB]: {
            "parameter_group_id": SCORER_PARAMETER_GROUP_UUIDS["advanced_llm_parameters"],
            "parameter_order_within_group": 3,
        },
    }
    build_components_parameters_assignments_to_parameter_groups(session, parameter_group_assignments)
