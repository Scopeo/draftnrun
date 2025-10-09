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
    upsert_component_categories,
    upsert_component_versions,
    upsert_components,
    upsert_components_parameter_definitions,
)
from ada_backend.database.seed.seed_categories import CATEGORY_UUIDS
from ada_backend.database.seed.seed_tool_description import TOOL_DESCRIPTION_UUIDS
from ada_backend.database.seed.utils import COMPONENT_UUIDS

FILTER_SCHEMA_PARAMETER_NAME = "filtering_json_schema"
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
        name="Filter",
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
        id=COMPONENT_UUIDS["filter"],
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
    upsert_components_parameter_definitions(
        session=session,
        component_parameter_definitions=[
            db.ComponentParameterDefinition(
                id=UUID("59443366-5b1f-5543-9fc5-57378f9aaf6e"),
                component_version_id=filter_version.id,
                name=FILTER_SCHEMA_PARAMETER_NAME,
                type=ParameterType.STRING,
                nullable=False,
                default=json.dumps(DEFAULT_OUTPUT_FORMAT, indent=4),
                ui_component=UIComponent.TEXTAREA,
                ui_component_properties=UIComponentProperties(
                    label="""Filtering schema to apply""",
                    description="Describe here the schema for filtering the final workflow response."
                    " Must be a correct json schema. The output will be validated against this schema"
                    " and filtered to only include the specified fields.",
                ).model_dump(exclude_unset=True, exclude_none=True),
            ),
        ],
    )

    upsert_component_categories(
        session=session,
        component_id=filter.id,
        category_ids=[CATEGORY_UUIDS["processing"]],
    )
