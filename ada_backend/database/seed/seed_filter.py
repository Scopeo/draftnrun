from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.component_definition_seeding import (
    upsert_component_categories,
    upsert_component_versions,
    upsert_components,
    upsert_release_stage_to_current_version_mapping,
)
from ada_backend.database.seed.seed_categories import CATEGORY_UUIDS
from ada_backend.database.seed.seed_tool_description import TOOL_DESCRIPTION_UUIDS
from ada_backend.database.seed.utils import COMPONENT_UUIDS, COMPONENT_VERSION_UUIDS

DEFAULT_OUTPUT_FORMAT = {
    "type": "object",
    "title": "AgentPayload",
    "properties": {
        "messages": {
            "type": "array",
            "items": {
                "type": "ChatMessage",
                "properties": {
                    "role": {"type": "string"},
                    "content": {"anyOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}]},
                    "tool_calls": {"type": "array", "items": {"type": "object"}},
                    "tool_call_id": {"type": "string"},
                },
                "required": ["role"],
            },
        },
        "error": {"type": "string"},
        "artifacts": {
            "type": "object",
            "properties": {
                "sources": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "title": "SourceChunk",
                        "properties": {
                            "name": {"type": "string"},
                            "document_name": {"type": "string"},
                            "content": {"type": "string"},
                            "url": {"type": "string"},
                            "url_display_type": {
                                "type": "string",
                                "enum": ["blank", "download", "viewer", "no_show"],
                                "default": "viewer",
                            },
                            "metadata": {"type": "object", "additionalProperties": True},
                        },
                        "required": ["name", "document_name", "content"],
                    },
                }
            },
            "additionalProperties": True,
        },
        "is_final": {"type": "boolean"},
    },
    "required": ["messages"],
}


def seed_filter_components(session: Session):
    filter = db.Component(
        id=COMPONENT_UUIDS["filter"],
        name="Json Filter",
        is_agent=True,
        is_protected=True,
        icon="tabler-json",
    )
    upsert_components(
        session=session,
        components=[
            filter,
        ],
    )
    filter_version = db.ComponentVersion(
        id=COMPONENT_VERSION_UUIDS["filter"],
        component_id=COMPONENT_UUIDS["filter"],
        version_tag="0.0.1",
        release_stage=db.ReleaseStage.PUBLIC,
        description="Filter: takes a json and filters it according to a given json schema",
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["default_filter_tool_description"],
    )
    upsert_component_versions(
        session=session,
        component_versions=[filter_version],
    )
    # LEGACY: Manual port seeding for unmigrated Filter component
    existing = session.query(db.ComponentVersion).filter(db.ComponentVersion.id == filter_version.id).first()
    if existing:
        # Ensure INPUT and OUTPUT canonical 'messages' ports exist
        port_defs = (
            session.query(db.PortDefinition).filter(db.PortDefinition.component_version_id == filter_version.id).all()
        )
        have_messages_input = any(pd.port_type == db.PortType.INPUT and pd.name == "messages" for pd in port_defs)
        have_messages_output = any(pd.port_type == db.PortType.OUTPUT and pd.name == "messages" for pd in port_defs)

        if not have_messages_input:
            session.add(
                db.PortDefinition(
                    component_version_id=filter_version.id,
                    name="messages",
                    port_type=db.PortType.INPUT,
                    is_canonical=True,
                    description="Canonical input carrying chat messages",
                )
            )
        if not have_messages_output:
            session.add(
                db.PortDefinition(
                    component_version_id=filter_version.id,
                    name="messages",
                    port_type=db.PortType.OUTPUT,
                    is_canonical=True,
                    description="Canonical output carrying chat messages",
                )
            )
        session.commit()

    # Create release stage mapping
    upsert_release_stage_to_current_version_mapping(
        session=session,
        component_id=filter_version.component_id,
        release_stage=filter_version.release_stage,
        component_version_id=filter_version.id,
    )

    upsert_component_categories(
        session=session,
        component_id=filter.id,
        category_ids=[CATEGORY_UUIDS["workflow_logic"]],
    )
