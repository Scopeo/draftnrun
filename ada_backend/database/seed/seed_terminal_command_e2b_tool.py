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


def seed_terminal_command_e2b_components(session: Session):
    terminal_command_e2b_component = Component(
        id=COMPONENT_UUIDS["terminal_command_e2b"],
        name="Terminal Command E2B",
        description="Execute terminal commands in a secure sandbox environment.",
        is_agent=False,
        function_callable=True,
        can_use_function_calling=False,
        release_stage=db.ReleaseStage.BETA,
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["terminal_command_e2b_tool_description"],
    )
    upsert_components(session, [terminal_command_e2b_component])

    terminal_command_e2b_parameter_definitions = [
        ComponentParameterDefinition(
            id=UUID("e2b10001-1111-2222-3333-444444444444"),
            component_id=terminal_command_e2b_component.id,
            name="timeout",
            type=ParameterType.INTEGER,
            nullable=False,
            default=60,
            ui_component=UIComponent.SLIDER,
            ui_component_properties=UIComponentProperties(
                label="Command Timeout (seconds)",
                min=10,
                max=600,
                step=10,
                placeholder="60",
                description="Maximum time for command execution. Default is 60 seconds.",
            ).model_dump(exclude_unset=True, exclude_none=True),
            is_advanced=True,
        ),
    ]

    upsert_components_parameter_definitions(session, terminal_command_e2b_parameter_definitions)
