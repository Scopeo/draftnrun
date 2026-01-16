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


def seed_python_code_runner_components(session: Session):
    python_code_runner_component = Component(
        id=COMPONENT_UUIDS["python_code_runner"],
        name="Code Execution (Python)",
        is_agent=False,
        function_callable=True,
        can_use_function_calling=False,
        icon="logos-python",
    )
    upsert_components(session, [python_code_runner_component])

    python_code_runner_component_version = db.ComponentVersion(
        id=COMPONENT_VERSION_UUIDS["python_code_runner"],
        component_id=COMPONENT_UUIDS["python_code_runner"],
        version_tag="0.0.1",
        release_stage=db.ReleaseStage.PUBLIC,
        description="Execute Python code in a secure sandbox environment.",
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["python_code_runner_tool_description"],
    )
    upsert_component_versions(
        session=session,
        component_versions=[python_code_runner_component_version],
    )

    python_code_runner_parameter_definitions = [
        ComponentParameterDefinition(
            id=UUID("e2b00002-2222-3333-4444-555555555555"),
            component_version_id=python_code_runner_component_version.id,
            name="timeout",
            type=ParameterType.INTEGER,
            nullable=False,
            default=300,
            ui_component=UIComponent.SLIDER,
            ui_component_properties=UIComponentProperties(
                label="Sandbox Timeout (seconds)",
                min=60,
                max=1800,
                step=60,
                placeholder="300",
                description="Maximum time the sandbox can stay alive. Default is 300 seconds (5 minutes).",
            ).model_dump(exclude_unset=True, exclude_none=True),
            is_advanced=True,
        ),
    ]

    upsert_components_parameter_definitions(session, python_code_runner_parameter_definitions)

    # Create release stage mapping
    upsert_release_stage_to_current_version_mapping(
        session=session,
        component_id=python_code_runner_component_version.component_id,
        release_stage=python_code_runner_component_version.release_stage,
        component_version_id=python_code_runner_component_version.id,
    )

    upsert_component_categories(
        session=session,
        component_id=python_code_runner_component.id,
        category_ids=[CATEGORY_UUIDS["run_code"]],
    )
