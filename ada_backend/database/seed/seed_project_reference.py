from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.models import ParameterType, UIComponent, UIComponentProperties
from ada_backend.database.component_definition_seeding import (
    upsert_component_versions,
    upsert_components,
    upsert_components_parameter_definitions,
)
from ada_backend.database.seed.utils import COMPONENT_UUIDS


def seed_project_reference_components(session: Session):
    """Seed the ProjectReference component definition."""

    project_reference = db.Component(
        id=COMPONENT_UUIDS["project_reference"],
        name="ProjectReference",
        is_agent=True,
        function_callable=False,
        icon="tabler-link",
    )

    upsert_components(
        session=session,
        components=[project_reference],
    )

    project_reference_version = db.ComponentVersion(
        id=COMPONENT_UUIDS["project_reference"],
        component_id=COMPONENT_UUIDS["project_reference"],
        version_tag="1.0.0",
        release_stage=db.ReleaseStage.INTERNAL,
        description="Execute another project's graph workflow as a component.",
    )
    upsert_component_versions(session=session, component_versions=[project_reference_version])

    upsert_components_parameter_definitions(
        session=session,
        component_parameter_definitions=[
            db.ComponentParameterDefinition(
                id=UUID("47d2e1f5-8c39-4a6b-9f15-3e8a7c2d1b90"),
                component_version_id=project_reference_version.id,
                name="project_id",
                type=ParameterType.STRING,
                nullable=False,
                # TODO: Dropdown to choose among existing projects (that are accessible to the user)
                ui_component=UIComponent.TEXTFIELD,
                ui_component_properties=UIComponentProperties(
                    label="Project ID",
                    placeholder="Enter the UUID of the project to reference",
                    description=(
                        "The UUID of the project whose graph workflow will be executed. "
                        "The project must be published to production."
                    ),
                ).model_dump(exclude_unset=True, exclude_none=True),
            ),
            # TODO: Add version, now it can only reference the latest "production" version
        ],
    )
