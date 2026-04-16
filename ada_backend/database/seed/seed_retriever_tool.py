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
from ada_backend.database.models import ParameterType, SelectOption, UIComponent, UIComponentProperties
from ada_backend.database.seed.seed_categories import CATEGORY_UUIDS
from ada_backend.database.seed.seed_tool_description import TOOL_DESCRIPTION_UUIDS
from ada_backend.database.seed.utils import COMPONENT_UUIDS, COMPONENT_VERSION_UUIDS


def seed_retriever_tool_components(session: Session):
    retriever_tool = db.Component(
        id=COMPONENT_UUIDS["retriever_tool"],
        name="Knowledge Search (Retriever)",
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

    upsert_release_stage_to_current_version_mapping(
        session=session,
        component_id=retriever_tool_version.component_id,
        release_stage=retriever_tool_version.release_stage,
        component_version_id=retriever_tool_version.id,
    )

    upsert_component_categories(
        session=session,
        component_id=retriever_tool.id,
        category_ids=[CATEGORY_UUIDS["search_engine"]],
    )

    # --- Retriever Tool v2 (adds search_mode parameter) ---
    retriever_tool_v2_version = db.ComponentVersion(
        id=COMPONENT_VERSION_UUIDS["retriever_tool_v2"],
        component_id=COMPONENT_UUIDS["retriever_tool"],
        version_tag="0.0.2",
        release_stage=db.ReleaseStage.INTERNAL,
        description="Retrieve relevant document chunks from a knowledge base with configurable search mode.",
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["default_retriever_tool_description"],
    )
    upsert_component_versions(session, [retriever_tool_v2_version])

    upsert_components_parameter_definitions(
        session=session,
        component_parameter_definitions=[
            db.ComponentParameterDefinition(
                id=UUID("d76b5ffc-2cfa-48cd-832f-713d551fad60"),
                component_version_id=retriever_tool_v2_version.id,
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
            ),
            db.ComponentParameterDefinition(
                id=UUID("7f4e50ff-09bc-43f0-aad5-b9b0a384648c"),
                component_version_id=retriever_tool_v2_version.id,
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
            ),
            db.ComponentParameterDefinition(
                id=UUID("7422b4d8-1912-4acb-8caa-989daec85a0c"),
                component_version_id=retriever_tool_v2_version.id,
                name="search_mode",
                type=ParameterType.STRING,
                nullable=False,
                default="semantic",
                ui_component=UIComponent.SELECT,
                ui_component_properties=UIComponentProperties(
                    label="Search Mode",
                    description="How the system searches your knowledge base. "
                    "'Hybrid' finds results by combining meaning-based and exact word matching for the best "
                    "accuracy. "
                    "'Semantic' finds results based on meaning and context. "
                    "'Keyword' finds results based on exact word matches.",
                    options=[
                        SelectOption(value="hybrid", label="Hybrid"),
                        SelectOption(value="semantic", label="Semantic"),
                        SelectOption(value="keyword", label="Keyword"),
                    ],
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=False,
            ),
            db.ComponentParameterDefinition(
                id=UUID("b4970083-165a-43f2-bee8-85e5a93737cf"),
                component_version_id=retriever_tool_v2_version.id,
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
            ),
            db.ComponentParameterDefinition(
                id=UUID("81d4f85d-8e35-496b-bbc1-ec324c93783b"),
                component_version_id=retriever_tool_v2_version.id,
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
            ),
            db.ComponentParameterDefinition(
                id=UUID("75cb5ebc-a3ef-4301-a1eb-97b7380eb02c"),
                component_version_id=retriever_tool_v2_version.id,
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
            ),
            db.ComponentParameterDefinition(
                id=UUID("eda8bfcd-006a-402a-b728-7ea493079884"),
                component_version_id=retriever_tool_v2_version.id,
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
                        "The system will check each field in order and use the first valid (non-null) date "
                        "it finds. This date is used to calculate the chunk's age when applying penalties."
                    ),
                    placeholder="Enter the date field here",
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=True,
            ),
            db.ComponentParameterDefinition(
                id=UUID("b69a1151-ac12-4855-b831-2ee21db29fdf"),
                component_version_id=retriever_tool_v2_version.id,
                name="retrieved_chunks_before_applying_penalty",
                type=ParameterType.INTEGER,
                nullable=True,
                default="10",
                ui_component=UIComponent.TEXTFIELD,
                ui_component_properties=UIComponentProperties(
                    label="Max Retrieved Chunks Before Applying Penalty",
                    description="The maximum number of chunks to retrieve before applying date penalty. "
                    "This sets the upper limit for how many chunks will be returned before applying "
                    "penalties.",
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=True,
            ),
        ],
    )

    upsert_release_stage_to_current_version_mapping(
        session=session,
        component_id=retriever_tool_v2_version.component_id,
        release_stage=retriever_tool_v2_version.release_stage,
        component_version_id=retriever_tool_v2_version.id,
    )
