from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.models import ParameterType, UIComponent, UIComponentProperties, SelectOption
from ada_backend.database.component_definition_seeding import (
    upsert_components,
    upsert_components_parameter_definitions,
)
from ada_backend.database.seed.seed_tool_description import TOOL_DESCRIPTION_UUIDS
from ada_backend.database.seed.utils import COMPONENT_UUIDS


def seed_project_reference_components(session: Session):
    """Seed the ProjectReference component definition."""

    project_reference = db.Component(
        id=COMPONENT_UUIDS["project_reference"],
        name="ProjectReference",
        description="Execute another project's graph workflow as a component",
        is_agent=True,
        function_callable=True,
        release_stage=db.ReleaseStage.INTERNAL,
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["default_project_reference_tool_description"],
    )

    upsert_components(
        session=session,
        components=[project_reference],
    )

    upsert_components_parameter_definitions(
        session=session,
        component_parameter_definitions=[
            db.ComponentParameterDefinition(
                id=UUID("47d2e1f5-8c39-4a6b-9f15-3e8a7c2d1b90"),
                component_id=project_reference.id,
                name="project_id",
                type=ParameterType.STRING,
                nullable=False,
                # TODO: Dropdown to choose among existing projects (that are accessible to the user)
                ui_component=UIComponent.TEXTFIELD,
                ui_component_properties=UIComponentProperties(
                    label="Project ID",
                    placeholder="Enter the UUID of the project to reference",
                    description="The UUID of the project whose graph workflow will be executed",
                ).model_dump(exclude_unset=True, exclude_none=True),
            ),
            # TODO: Change to version
            db.ComponentParameterDefinition(
                id=UUID("b8f3c2d1-4e5a-4b6c-9d7e-1f2a3b4c5d6e"),
                component_id=project_reference.id,
                name="env",
                type=ParameterType.STRING,
                nullable=False,
                default="production",
                ui_component=UIComponent.SELECT,
                ui_component_properties=UIComponentProperties(
                    options=[
                        SelectOption(value="production", label="Production"),
                        SelectOption(value="draft", label="Draft"),
                    ],
                    label="Environment",
                    description="Select which environment of the project to execute",
                ).model_dump(exclude_unset=True, exclude_none=True),
            ),
        ],
    )
