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


def seed_e2b_components(session: Session):
    e2b_component = Component(
        id=COMPONENT_UUIDS["e2b_python_sandbox"],
        name="E2B Python Sandbox",
        description="Execute Python code in a secure sandbox environment using E2B.",
        is_agent=False,
        function_callable=True,
        can_use_function_calling=False,
        release_stage=db.ReleaseStage.BETA,
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["e2b_tool_description"],
    )
    upsert_components(session, [e2b_component])

    e2b_parameter_definitions = [
        ComponentParameterDefinition(
            id=UUID("e2b00001-1111-2222-3333-444444444444"),
            component_id=e2b_component.id,
            name="e2b_api_key",
            type=ParameterType.LLM_API_KEY,
            nullable=True,
            ui_component=UIComponent.TEXTFIELD,
            ui_component_properties=UIComponentProperties(
                label="E2B API Key",
                placeholder="e2b_***",
                description="Your E2B API key for sandbox access. If not provided, will use E2B_API_KEY environment variable.",
            ).model_dump(exclude_unset=True, exclude_none=True),
        ),
        ComponentParameterDefinition(
            id=UUID("e2b00002-2222-3333-4444-555555555555"),
            component_id=e2b_component.id,
            name="sandbox_timeout",
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

    upsert_components_parameter_definitions(session, e2b_parameter_definitions)