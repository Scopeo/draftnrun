from uuid import UUID
import json

from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.models import (
    ParameterType,
    UIComponent,
    UIComponentProperties,
)
from ada_backend.database.component_definition_seeding import (
    upsert_component_versions,
    upsert_components,
    upsert_components_parameter_definitions,
    upsert_release_stage_to_current_version_mapping,
)

from ada_backend.repositories.component_repository import get_component_version_by_id
from ada_backend.repositories.component_repository import get_component_by_id
from ada_backend.database.seed.seed_tool_description import TOOL_DESCRIPTION_UUIDS
from ada_backend.database.seed.utils import COMPONENT_UUIDS


START_PAYLOAD_PARAMETER_NAME = "payload_schema"


def seed_start_components(session: Session):
    start_component = db.Component(
        id=COMPONENT_UUIDS["start"],
        name="Start",
        is_agent=True,
        is_protected=True,
        icon="tabler-play",
    )
    upsert_components(
        session=session,
        components=[
            start_component,
        ],
    )
    start_version = db.ComponentVersion(
        id=COMPONENT_UUIDS["start"],
        component_id=COMPONENT_UUIDS["start"],
        version_tag="0.0.1",
        release_stage=db.ReleaseStage.PUBLIC,
        description="Beginning of the workflow: setup the input format here.",
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["default_tool_description"],
    )
    upsert_component_versions(
        session=session,
        component_versions=[start_version],
    )
    # LEGACY: Manual port seeding for unmigrated Input component

    existing = get_component_version_by_id(session, start_version.id)
    if existing:
        # Ensure an OUTPUT canonical 'messages' port exists
        port_defs = (
            session.query(db.PortDefinition).filter(db.PortDefinition.component_version_id == start_version.id).all()
        )
    existing = get_component_by_id(session, start_component.id)
    if existing:
        # Ensure an OUTPUT canonical 'messages' port exists
        port_defs = session.query(db.PortDefinition).filter(db.PortDefinition.component_id == start_component.id).all()
        have_messages_output = any(pd.port_type == db.PortType.OUTPUT and pd.name == "messages" for pd in port_defs)
        if not have_messages_output:
            session.add(
                db.PortDefinition(
                    component_version_id=start_version.id,
                    name="messages",
                    port_type=db.PortType.OUTPUT,
                    is_canonical=True,
                    description="Canonical output carrying chat messages",
                )
            )
            session.commit()
    upsert_components_parameter_definitions(
        session=session,
        component_parameter_definitions=[
            db.ComponentParameterDefinition(
                id=UUID("48332255-4a0e-4432-8fb4-46267e8ffd4d"),
                component_version_id=start_version.id,
                name=START_PAYLOAD_PARAMETER_NAME,
                type=ParameterType.STRING,
                nullable=False,
                default=json.dumps(
                    {"messages": [{"role": "user", "content": "Hello"}], "additional_info": "info"}, indent=4
                ),
                ui_component=UIComponent.TEXTAREA,
                ui_component_properties=UIComponentProperties(
                    label="""An example of your payload schema""",
                    description="Provide an example of the payload schema for your workflow input. "
                    "This must be valid JSON. The keys of this dictionary can be referenced in subsequent components "
                    "as variables, for example: {{additional_info}}",
                ).model_dump(exclude_unset=True, exclude_none=True),
            ),
        ],
    )

    # Create release stage mapping
    upsert_release_stage_to_current_version_mapping(
        session=session,
        component_id=start_version.component_id,
        release_stage=start_version.release_stage,
        component_version_id=start_version.id,
    )
