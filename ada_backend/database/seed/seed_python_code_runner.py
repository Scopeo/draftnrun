from uuid import UUID
from sqlalchemy.orm import Session

from ada_backend.database.models import (
    Component,
    ComponentParameterDefinition,
    UIComponent,
    UIComponentProperties,
    ParameterType,
)
from ada_backend.database.component_definition_seeding import (
    upsert_components,
    upsert_components_parameter_definitions,
)
from ada_backend.database.seed.utils import COMPONENT_UUIDS
from ada_backend.database.seed.seed_tool_description import TOOL_DESCRIPTION_UUIDS
from ada_backend.database import models as db


def seed_python_code_runner_components(session: Session):
    python_code_runner_component = Component(
        id=COMPONENT_UUIDS["python_code_runner"],
        name="Python Code Runner",
        description="Execute Python code in a secure sandbox environment.",
        is_agent=False,
        function_callable=True,
        can_use_function_calling=False,
        release_stage=db.ReleaseStage.BETA,
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["python_code_runner_tool_description"],
    )
    upsert_components(session, [python_code_runner_component])

    python_code_runner_parameter_definitions = [
        ComponentParameterDefinition(
            id=UUID("e2b00002-2222-3333-4444-555555555555"),
            component_id=python_code_runner_component.id,
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
