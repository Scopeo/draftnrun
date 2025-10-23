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
    upsert_component_versions,
    upsert_components,
    upsert_components_parameter_definitions,
    upsert_component_categories,
)
from ada_backend.database.seed.seed_categories import CATEGORY_UUIDS
from ada_backend.database.seed.utils import COMPONENT_UUIDS
from ada_backend.database.seed.seed_tool_description import TOOL_DESCRIPTION_UUIDS
from ada_backend.database import models as db


def seed_terminal_command_runner_components(session: Session):
    terminal_command_runner_component = Component(
        id=COMPONENT_UUIDS["terminal_command_runner"],
        name="Terminal Command Runner",
        is_agent=False,
        function_callable=True,
        can_use_function_calling=False,
    )
    upsert_components(session, [terminal_command_runner_component])
    terminal_command_runner_version = db.ComponentVersion(
        id=COMPONENT_UUIDS["terminal_command_runner"],
        component_id=COMPONENT_UUIDS["terminal_command_runner"],
        version_tag="1.0.0",
        release_stage=db.ReleaseStage.PUBLIC,
        description="Execute terminal commands in a secure sandbox environment.",
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["terminal_command_runner_tool_description"],
    )
    upsert_component_versions(
        session=session,
        component_versions=[terminal_command_runner_version],
        icon="tabler-terminal-2",
    )

    terminal_command_runner_parameter_definitions = [
        ComponentParameterDefinition(
            id=UUID("e2b10001-1111-2222-3333-444444444444"),
            component_version_id=terminal_command_runner_version.id,
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

    upsert_components_parameter_definitions(session, terminal_command_runner_parameter_definitions)
    upsert_component_categories(
        session=session,
        component_id=terminal_command_runner_component.id,
        category_ids=[CATEGORY_UUIDS["processing"]],
    )
