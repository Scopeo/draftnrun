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


def seed_chunk_processor_components(session: Session):
    """Seed the ChunkProcessor component definition."""

    chunk_processor = db.Component(
        id=COMPONENT_UUIDS["chunk_processor"],
        name="ChunkProcessor",
        is_agent=True,
        function_callable=False,
    )

    upsert_components(
        session=session,
        components=[chunk_processor],
    )

    chunk_processor_version = db.ComponentVersion(
        id=COMPONENT_UUIDS["chunk_processor"],
        component_id=chunk_processor.id,
        description="Process data in chunks using a project's graph workflow",
        release_stage=db.ReleaseStage.INTERNAL,
        version_tag="1.0.0",
    )
    upsert_component_versions(
        session=session,
        component_versions=[chunk_processor_version],
    )

    upsert_components_parameter_definitions(
        session=session,
        component_parameter_definitions=[
            db.ComponentParameterDefinition(
                id=UUID("6e8f1a2b-3c4d-5e6f-7a8b-9c0d1e2f3a4b"),
                component_version_id=chunk_processor_version.id,
                name="project_id",
                type=ParameterType.STRING,
                nullable=False,
                ui_component=UIComponent.TEXTFIELD,
                ui_component_properties=UIComponentProperties(
                    label="Project ID",
                    placeholder="Enter the UUID of the project to reference",
                    description="The UUID of the project whose graph workflow will be executed on each chunk",
                    type="",
                ).model_dump(exclude_unset=True, exclude_none=True),
            ),
            db.ComponentParameterDefinition(
                id=UUID("8a0f3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d"),
                component_version_id=chunk_processor_version.id,
                name="split_char",
                type=ParameterType.STRING,
                nullable=False,
                default="\\n\\n",
                ui_component=UIComponent.TEXTFIELD,
                ui_component_properties=UIComponentProperties(
                    label="Split Character",
                    placeholder="\\n\\n",
                    description="Delimiter used to split the input into chunks",
                    type="",
                ).model_dump(exclude_unset=True, exclude_none=True),
            ),
            db.ComponentParameterDefinition(
                id=UUID("ac2f5e6f-7a8b-9c0d-1e2f-3a4b5c6d7e8f"),
                component_version_id=chunk_processor_version.id,
                name="join_char",
                type=ParameterType.STRING,
                nullable=False,
                default="\\n\\n",
                ui_component=UIComponent.TEXTFIELD,
                ui_component_properties=UIComponentProperties(
                    label="Join Character",
                    placeholder="\\n\\n",
                    description="Character or string to join the processed chunks with",
                    type="",
                ).model_dump(exclude_unset=True, exclude_none=True),
            ),
        ],
    )
