from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.component_definition_seeding import (
    upsert_component_categories,
    upsert_component_versions,
    upsert_components,
    upsert_components_parameter_definitions,
    upsert_release_stage_to_current_version_mapping,
)
from ada_backend.database.models import ParameterType, UIComponent, UIComponentProperties
from ada_backend.database.seed.seed_categories import CATEGORY_UUIDS
from ada_backend.database.seed.seed_tool_description import TOOL_DESCRIPTION_UUIDS
from ada_backend.database.seed.utils import COMPONENT_UUIDS, COMPONENT_VERSION_UUIDS


def seed_retriever_tool_components(session: Session):
    retriever_tool = db.Component(
        id=COMPONENT_UUIDS["retriever_tool"],
        name="Knowledge Base Search",
        is_agent=True,
        function_callable=True,
        icon="tabler-database-search",
    )

    upsert_components(
        session=session,
        components=[retriever_tool],
    )

    retriever_tool_version = db.ComponentVersion(
        id=COMPONENT_VERSION_UUIDS["retriever_tool"],
        component_id=COMPONENT_UUIDS["retriever_tool"],
        version_tag="0.0.1",
        release_stage=db.ReleaseStage.PUBLIC,
        description="Retrieve relevant document chunks from a knowledge base using semantic search.",
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["default_retriever_tool_description"],
    )
    upsert_component_versions(session, [retriever_tool_version])

    data_source_param = db.ComponentParameterDefinition(
        id=UUID("9a1b2c3d-4e5f-6789-0abc-def123456789"),
        component_version_id=retriever_tool_version.id,
        name="data_source",
        type=ParameterType.DATA_SOURCE,
        nullable=False,
        default=None,
        ui_component=UIComponent.SELECT,
        ui_component_properties=UIComponentProperties(
            label="Data Source",
            description="The data source from which to retrieve chunks. This includes the collection "
            "name and embedding model.",
        ).model_dump(exclude_unset=True, exclude_none=True),
        is_advanced=False,
    )

    number_of_chunks_param = db.ComponentParameterDefinition(
        id=UUID("8b2c3d4e-5f67-8901-bcde-f234567890ab"),
        component_version_id=retriever_tool_version.id,
        name="number_of_chunks",
        type=ParameterType.INTEGER,
        nullable=False,
        default="10",
        ui_component=UIComponent.TEXTFIELD,
        ui_component_properties=UIComponentProperties(
            label="Number of Chunks",
            description="Number of chunks to retrieve from the knowledge base.",
        ).model_dump(exclude_unset=True, exclude_none=True),
        is_advanced=False,
    )

    enable_date_penalty_param = db.ComponentParameterDefinition(
        id=UUID("7c3d4e5f-6789-0123-cdef-4567890abc12"),
        component_version_id=retriever_tool_version.id,
        name="enable_date_penalty_for_chunks",
        type=ParameterType.BOOLEAN,
        nullable=False,
        default="False",
        ui_component=UIComponent.CHECKBOX,
        ui_component_properties=UIComponentProperties(
            label="Enable Date Penalty",
            description="Enable penalty for older chunks based on their date.",
        ).model_dump(exclude_unset=True, exclude_none=True),
        is_advanced=True,
    )

    chunk_age_penalty_rate_param = db.ComponentParameterDefinition(
        id=UUID("6d4e5f67-8901-2345-def6-7890abc123de"),
        component_version_id=retriever_tool_version.id,
        name="chunk_age_penalty_rate",
        type=ParameterType.FLOAT,
        nullable=True,
        default="0.1",
        ui_component=UIComponent.SLIDER,
        ui_component_properties=UIComponentProperties(
            min=0.0,
            max=1.0,
            step=0.01,
            marks=True,
            label="Penalty per Age",
            description="Determines how much to penalize older content chunks. "
            "A higher value means older chunks are penalized more.",
        ).model_dump(exclude_unset=True, exclude_none=True),
        is_advanced=True,
    )

    default_penalty_rate_param = db.ComponentParameterDefinition(
        id=UUID("5e6f7890-1234-5678-f901-234567def890"),
        component_version_id=retriever_tool_version.id,
        name="default_penalty_rate",
        type=ParameterType.FLOAT,
        nullable=True,
        default="0.1",
        ui_component=UIComponent.SLIDER,
        ui_component_properties=UIComponentProperties(
            min=0.0,
            max=1.0,
            step=0.01,
            marks=True,
            label="Default Penalty Rate",
            description="Used as a fallback penalty rate for chunks without a specific date. "
            "This allows you to decide how to deal with missing information.",
        ).model_dump(exclude_unset=True, exclude_none=True),
        is_advanced=True,
    )

    metadata_date_key_param = db.ComponentParameterDefinition(
        id=UUID("4f789012-3456-7890-1234-5678def90123"),
        component_version_id=retriever_tool_version.id,
        name="metadata_date_key",
        type=ParameterType.STRING,
        nullable=True,
        default="date",
        ui_component=UIComponent.TEXTFIELD,
        ui_component_properties=UIComponentProperties(
            label="Date field used for penalty",
            description=(
                "The metadata field(s) that contain the date information for each chunk. "
                "You can specify multiple date fields names as a comma-separated list "
                "(e.g., created_date,updated_date). "
                "The system will check each field in order and use the first valid (non-null) date it finds. "
                "This date is used to calculate the chunk's age when applying penalties."
            ),
            placeholder="Enter the date field here",
        ).model_dump(exclude_unset=True, exclude_none=True),
        is_advanced=True,
    )

    retrieved_chunks_before_applying_penalty_param = db.ComponentParameterDefinition(
        id=UUID("3f890123-4567-8901-2345-678def901234"),
        component_version_id=retriever_tool_version.id,
        name="retrieved_chunks_before_applying_penalty",
        type=ParameterType.INTEGER,
        nullable=True,
        default="10",
        ui_component=UIComponent.TEXTFIELD,
        ui_component_properties=UIComponentProperties(
            label="Max Retrieved Chunks Before Applying Penalty",
            description="The maximum number of chunks to retrieve before applying date penalty. "
            "This sets the upper limit for how many chunks will be returned before applying penalties. ",
        ).model_dump(exclude_unset=True, exclude_none=True),
        is_advanced=True,
    )

    upsert_components_parameter_definitions(
        session=session,
        component_parameter_definitions=[
            data_source_param,
            number_of_chunks_param,
            enable_date_penalty_param,
            chunk_age_penalty_rate_param,
            default_penalty_rate_param,
            metadata_date_key_param,
            retrieved_chunks_before_applying_penalty_param,
        ],
    )

    # Create release stage mapping
    upsert_release_stage_to_current_version_mapping(
        session=session,
        component_id=retriever_tool_version.component_id,
        release_stage=retriever_tool_version.release_stage,
        component_version_id=retriever_tool_version.id,
    )

    upsert_component_categories(
        session=session,
        component_id=retriever_tool.id,
        category_ids=[CATEGORY_UUIDS["query"]],
    )
