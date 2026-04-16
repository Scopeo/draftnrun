from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.component_definition_seeding import (
    upsert_component_versions,
    upsert_components_parameter_definitions,
    upsert_release_stage_to_current_version_mapping,
)
from ada_backend.database.models import ParameterType, SelectOption, UIComponent, UIComponentProperties
from ada_backend.database.seed.constants import (
    COMPLETION_MODEL_IN_DB,
    REASONING_IN_DB,
    TEMPERATURE_IN_DB,
    VERBOSITY_IN_DB,
)
from ada_backend.database.seed.seed_tool_description import TOOL_DESCRIPTION_UUIDS
from ada_backend.database.seed.utils import (
    COMPONENT_UUIDS,
    COMPONENT_VERSION_UUIDS,
    ParameterLLMConfig,
    build_completion_service_config_definitions,
    build_components_parameters_assignments_to_parameter_groups,
    build_parameters_group,
    build_parameters_group_definitions,
)
from engine.components.synthesizer_prompts import get_base_synthetizer_prompt_template

RAG_V4_PARAMETER_GROUP_UUIDS = {
    "knowledge_parameters": UUID("f1a23b4c-5d6e-7f80-9a1b-2c3d4e5f6a7b"),
    "advanced_knowledge_parameters": UUID("a2b34c5d-6e7f-8091-ab2c-3d4e5f6a7b8c"),
    "llm_parameters": UUID("b3c45d6e-7f80-91a2-bc3d-4e5f6a7b8c9d"),
    "advanced_llm_parameters": UUID("c4d56e7f-8091-a2b3-cd4e-5f6a7b8c9d0e"),
    "reranker_parameters": UUID("d5e67f80-91a2-b3c4-de5f-6a7b8c9d0e1f"),
    "vocabulary_search_parameters": UUID("e6f78091-a2b3-c4d5-ef6a-7b8c9d0e1f20"),
    "formatter_parameters": UUID("f70891a2-b3c4-d5e6-f07b-8c9d0e1f2031"),
}


def seed_rag_v4_components(session: Session):
    rag_agent_v4_version = db.ComponentVersion(
        id=COMPONENT_VERSION_UUIDS["rag_agent_v4"],
        component_id=COMPONENT_UUIDS["rag_agent"],
        version_tag="0.3.0",
        description=(
            "Knowledge Agent (RAG) for retrieving relevant information from knowledge bases "
            "using a single query input. Supports hybrid, semantic, and keyword search modes."
        ),
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["default_rag_tool_description"],
        release_stage=db.ReleaseStage.INTERNAL,
    )
    upsert_component_versions(session=session, component_versions=[rag_agent_v4_version])

    rag_v4_search_mode_param = db.ComponentParameterDefinition(
        id=UUID("452d5859-db93-43ce-a2b0-d072cd46e219"),
        component_version_id=rag_agent_v4_version.id,
        name="search_mode",
        type=ParameterType.STRING,
        nullable=False,
        default="semantic",
        ui_component=UIComponent.SELECT,
        ui_component_properties=UIComponentProperties(
            label="Search Mode",
            description="How the system searches your knowledge base. "
            "'Hybrid' finds results by combining meaning-based and exact word matching for the best accuracy. "
            "'Semantic' finds results based on meaning and context. "
            "'Keyword' finds results based on exact word matches.",
            options=[
                SelectOption(value="hybrid", label="Hybrid"),
                SelectOption(value="semantic", label="Semantic"),
                SelectOption(value="keyword", label="Keyword"),
            ],
        ).model_dump(exclude_unset=True, exclude_none=True),
        is_advanced=False,
    )

    upsert_components_parameter_definitions(
        session=session,
        component_parameter_definitions=[
            db.ComponentParameterDefinition(
                id=UUID("56f41bee-8473-415e-a1a5-6705b0af9fc0"),
                component_version_id=rag_agent_v4_version.id,
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
                id=UUID("e446cd9c-56ac-4f91-8b52-ea6f4340ee25"),
                component_version_id=rag_agent_v4_version.id,
                name="prompt_template",
                type=ParameterType.STRING,
                nullable=True,
                default=get_base_synthetizer_prompt_template(),
                ui_component=UIComponent.TEXTAREA,
                ui_component_properties=UIComponentProperties(
                    label="Prompt Template",
                    placeholder=(
                        "Enter your prompt template here. "
                        "Use {{context_str}} and {{query_str}} for variable substitution."
                    ),
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=False,
            ),
            db.ComponentParameterDefinition(
                id=UUID("84729d5d-4ee0-4f1e-abed-3b27283c8dc0"),
                component_version_id=rag_agent_v4_version.id,
                name="max_retrieved_chunks",
                type=ParameterType.INTEGER,
                nullable=True,
                default="10",
                ui_component=UIComponent.TEXTFIELD,
                ui_component_properties=UIComponentProperties(
                    label="Max Retrieved Chunks",
                    description=(
                        "The maximum number of chunks to retrieve before applying any filtering or penalties. "
                        "This sets the upper limit for how many chunks will be returned by the retrieval process."
                    ),
                    placeholder="Enter the maximum number of chunks here",
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=False,
            ),
            rag_v4_search_mode_param,
            db.ComponentParameterDefinition(
                id=UUID("4509b3b9-11df-4491-8441-e0c1bb23559b"),
                component_version_id=rag_agent_v4_version.id,
                name="enable_date_penalty_for_chunks",
                type=ParameterType.BOOLEAN,
                nullable=True,
                default="False",
                ui_component=UIComponent.CHECKBOX,
                ui_component_properties=UIComponentProperties(
                    label="Apply age based penalty",
                    description="When enabled, older content chunks will be penalized based on their age. "
                    "This helps prioritize more recent content.",
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=True,
            ),
            db.ComponentParameterDefinition(
                id=UUID("111d4a11-3722-4749-802e-dd1748dc050d"),
                component_version_id=rag_agent_v4_version.id,
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
                id=UUID("fdc91df9-9e4b-44b3-be2a-c8ba236741cf"),
                component_version_id=rag_agent_v4_version.id,
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
                id=UUID("66c18eb1-2653-465a-a435-8be8313f876c"),
                component_version_id=rag_agent_v4_version.id,
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
                id=UUID("8c9f7020-a65e-44da-a22e-0f6a19042dc0"),
                component_version_id=rag_agent_v4_version.id,
                name="max_retrieved_chunks_after_penalty",
                type=ParameterType.INTEGER,
                nullable=True,
                default="10",
                ui_component=UIComponent.TEXTFIELD,
                ui_component_properties=UIComponentProperties(
                    label="Max Retrieved Chunks After Penalty",
                    description=(
                        "The maximum number of chunks to retrieve after applying penalties. "
                        "This sets the upper limit for how many chunks will be returned in the final result."
                    ),
                    placeholder="Enter the maximum number of chunks here",
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=True,
            ),
            db.ComponentParameterDefinition(
                id=UUID("bb2c46c1-7c19-4b77-a3ce-8d1cb9b504ba"),
                component_version_id=rag_agent_v4_version.id,
                name="use_reranker",
                type=ParameterType.BOOLEAN,
                nullable=True,
                default="False",
                ui_component=UIComponent.CHECKBOX,
                ui_component_properties=UIComponentProperties(
                    label="Use Reranker",
                    description="Enable reranking of retrieved chunks using Cohere reranker to improve relevance.",
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=True,
            ),
            db.ComponentParameterDefinition(
                id=UUID("4aaa8fec-7a9a-4e04-a450-9d054699e7b7"),
                component_version_id=rag_agent_v4_version.id,
                name="cohere_model",
                type=ParameterType.STRING,
                nullable=True,
                default="rerank-multilingual-v3.0",
                ui_component=UIComponent.SELECT,
                ui_component_properties=UIComponentProperties(
                    options=[
                        SelectOption(value="rerank-v3.5", label="Rerank v3.5"),
                        SelectOption(value="rerank-multilingual-v3.0", label="Rerank Multilingual v3.0"),
                    ],
                    label="Cohere Model",
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=True,
            ),
            db.ComponentParameterDefinition(
                id=UUID("62788ddf-a40e-4e40-b332-47b689961805"),
                component_version_id=rag_agent_v4_version.id,
                name="score_threshold",
                type=ParameterType.FLOAT,
                nullable=True,
                default="0.0",
                ui_component=UIComponent.SLIDER,
                ui_component_properties=UIComponentProperties(
                    min=0.0, max=1.0, step=0.1, marks=True, label="Score Threshold"
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=True,
            ),
            db.ComponentParameterDefinition(
                id=UUID("e3489939-50e6-48f4-8806-08e7761669f2"),
                component_version_id=rag_agent_v4_version.id,
                name="num_doc_reranked",
                type=ParameterType.INTEGER,
                nullable=True,
                default="5",
                ui_component=UIComponent.SLIDER,
                ui_component_properties=UIComponentProperties(
                    min=1, max=10, step=1, marks=True, label="Number of Documents Reranked"
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=True,
            ),
            db.ComponentParameterDefinition(
                id=UUID("0bba7a67-c271-4558-b3ba-44ddbd536b0b"),
                component_version_id=rag_agent_v4_version.id,
                name="use_vocabulary_search",
                type=ParameterType.BOOLEAN,
                nullable=True,
                default="False",
                ui_component=UIComponent.CHECKBOX,
                ui_component_properties=UIComponentProperties(
                    label="Use Vocabulary Search",
                    description="Enable vocabulary search to enrich the RAG agent's context with glossary "
                    "definitions.",
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=True,
            ),
            db.ComponentParameterDefinition(
                id=UUID("7dd95b0c-f539-48b8-9c52-f96f32a781b9"),
                component_version_id=rag_agent_v4_version.id,
                name="vocabulary_context_data",
                type=ParameterType.STRING,
                nullable=True,
                default=None,
                ui_component=UIComponent.TEXTAREA,
                ui_component_properties=UIComponentProperties(
                    label="Vocabulary Context Data (Glossary)",
                    placeholder=(
                        "Enter your glossary data as JSON: "
                        '{"term": ["term1", "term2"], "definition": ["def1", "def2"]}'
                    ),
                    description="A JSON object containing vocabulary terms and their definitions. "
                    "Each term should correspond to its definition by index.",
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=True,
            ),
            db.ComponentParameterDefinition(
                id=UUID("409e7c43-8d73-48d6-b66f-b0506af915e7"),
                component_version_id=rag_agent_v4_version.id,
                name="fuzzy_threshold",
                type=ParameterType.INTEGER,
                nullable=True,
                default="90",
                ui_component=UIComponent.SLIDER,
                ui_component_properties=UIComponentProperties(
                    min=1,
                    max=100,
                    step=1,
                    marks=True,
                    label="Fuzzy Matching Threshold",
                    description=(
                        "Fuzzy matching finds approximate matches between strings. "
                        "A threshold of 100 means the term must match exactly. "
                        "Lower values allow for misspellings and variations."
                    ),
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=True,
            ),
            db.ComponentParameterDefinition(
                id=UUID("22c922fb-b917-4c1c-9bd4-f8f838e37a49"),
                component_version_id=rag_agent_v4_version.id,
                name="fuzzy_matching_candidates",
                type=ParameterType.INTEGER,
                nullable=True,
                default="10",
                ui_component=UIComponent.SLIDER,
                ui_component_properties=UIComponentProperties(
                    min=1, max=100, step=1, marks=True, label="Number of definitions to retrieve"
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=True,
            ),
            db.ComponentParameterDefinition(
                id=UUID("bb5c1ec8-aafa-46e0-9d83-97af786eadda"),
                component_version_id=rag_agent_v4_version.id,
                name="vocabulary_context_prompt_key",
                type=ParameterType.STRING,
                nullable=True,
                default="retrieved_definitions",
                ui_component=UIComponent.TEXTFIELD,
                ui_component_properties=UIComponentProperties(
                    label="Prompt key for vocabulary context injection",
                    description="Put {{retrieved_definitions}} in the Synthesizer prompt of your RAG to allow the "
                    "injection of retrieved definitions from your Glossary into the Synthesizer prompt "
                    "during a RAG call.",
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=True,
            ),
            db.ComponentParameterDefinition(
                id=UUID("75959c9f-c748-4503-9f94-44fd23116260"),
                component_version_id=rag_agent_v4_version.id,
                name="use_formatter",
                type=ParameterType.BOOLEAN,
                nullable=True,
                default="False",
                ui_component=UIComponent.CHECKBOX,
                ui_component_properties=UIComponentProperties(
                    label="Use Formatter",
                    description="Enable custom formatting of the RAG response with sources.",
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=True,
            ),
            db.ComponentParameterDefinition(
                id=UUID("026c2ca1-f702-43f2-a530-e485a80dbd9c"),
                component_version_id=rag_agent_v4_version.id,
                name="add_sources",
                type=ParameterType.BOOLEAN,
                nullable=True,
                default="False",
                ui_component=UIComponent.CHECKBOX,
                ui_component_properties=UIComponentProperties(
                    label="Add Sources",
                    description="When enabled, sources will be added to the formatted response.",
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=True,
            ),
            *build_completion_service_config_definitions(
                component_version_id=rag_agent_v4_version.id,
                params_to_seed=[
                    ParameterLLMConfig(
                        param_name=COMPLETION_MODEL_IN_DB,
                        param_id=UUID("7af4208e-e8a0-46fc-87c7-34d3123afa11"),
                    ),
                    ParameterLLMConfig(
                        param_name=TEMPERATURE_IN_DB,
                        param_id=UUID("b71a67b7-c634-4c02-b13e-707709fce859"),
                    ),
                    ParameterLLMConfig(
                        param_name=VERBOSITY_IN_DB,
                        param_id=UUID("01f50b86-bef8-462d-9a6d-1f993147e944"),
                    ),
                    ParameterLLMConfig(
                        param_name=REASONING_IN_DB,
                        param_id=UUID("7d035202-1639-4264-bab3-f5595748879d"),
                    ),
                    ParameterLLMConfig(
                        param_name="api_key",
                        param_id=UUID("ad832572-d5f8-49f8-820a-5c9933aa04ab"),
                    ),
                ],
            ),
        ],
    )

    upsert_release_stage_to_current_version_mapping(
        session=session,
        component_id=rag_agent_v4_version.component_id,
        release_stage=rag_agent_v4_version.release_stage,
        component_version_id=rag_agent_v4_version.id,
    )

    retriever_v2_version = db.ComponentVersion(
        id=COMPONENT_VERSION_UUIDS["retriever_v2"],
        component_id=COMPONENT_UUIDS["retriever"],
        version_tag="0.0.2",
        description="Retriever with configurable search mode (semantic, keyword, or hybrid).",
        release_stage=db.ReleaseStage.INTERNAL,
    )
    upsert_component_versions(session=session, component_versions=[retriever_v2_version])

    upsert_components_parameter_definitions(
        session=session,
        component_parameter_definitions=[
            db.ComponentParameterDefinition(
                id=UUID("a1d2e3f4-5678-9abc-def0-112233445566"),
                component_version_id=retriever_v2_version.id,
                name="data_source",
                type=ParameterType.DATA_SOURCE,
                nullable=False,
                ui_component=UIComponent.SELECT,
                ui_component_properties=UIComponentProperties(
                    label="Data Source",
                    description="The data source from which to retrieve chunks.",
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=False,
            ),
            db.ComponentParameterDefinition(
                id=UUID("b2e3f4a5-6789-abcd-ef01-223344556677"),
                component_version_id=retriever_v2_version.id,
                name="max_retrieved_chunks",
                type=ParameterType.INTEGER,
                nullable=False,
                default="10",
                ui_component=UIComponent.TEXTFIELD,
                ui_component_properties=UIComponentProperties(
                    label="Max Retrieved Chunks",
                    description=(
                        "The maximum number of chunks to retrieve before applying any filtering or penalties. "
                        "This sets the upper limit for how many chunks will be returned by the retrieval process."
                    ),
                    placeholder="Enter the maximum number of chunks here",
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=False,
            ),
            db.ComponentParameterDefinition(
                id=UUID("c3f4a5b6-789a-bcde-f012-334455667788"),
                component_version_id=retriever_v2_version.id,
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
                id=UUID("d4a5b6c7-89ab-cdef-0123-445566778899"),
                component_version_id=retriever_v2_version.id,
                name="enable_date_penalty_for_chunks",
                type=ParameterType.BOOLEAN,
                nullable=True,
                default="False",
                ui_component=UIComponent.CHECKBOX,
                ui_component_properties=UIComponentProperties(
                    label="Apply age based penalty",
                    description="When enabled, older content chunks will be penalized based on their age. "
                    "This helps prioritize more recent content.",
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=True,
            ),
            db.ComponentParameterDefinition(
                id=UUID("e5b6c7d8-9abc-def0-1234-556677889900"),
                component_version_id=retriever_v2_version.id,
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
                id=UUID("f6c7d8e9-abcd-ef01-2345-667788990011"),
                component_version_id=retriever_v2_version.id,
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
                id=UUID("a7d8e9f0-bcde-f012-3456-778899001122"),
                component_version_id=retriever_v2_version.id,
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
                id=UUID("b8e9f0a1-cdef-0123-4567-889900112233"),
                component_version_id=retriever_v2_version.id,
                name="max_retrieved_chunks_after_penalty",
                type=ParameterType.INTEGER,
                nullable=True,
                default="10",
                ui_component=UIComponent.TEXTFIELD,
                ui_component_properties=UIComponentProperties(
                    label="Max Retrieved Chunks After Penalty",
                    description=(
                        "The maximum number of chunks to retrieve after applying penalties. "
                        "This sets the upper limit for how many chunks will be returned in the final result. "
                        "Note: this value should be less than or equal to the maximum number "
                        "of retrieved chunks before penalty."
                    ),
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=True,
            ),
        ],
    )

    upsert_release_stage_to_current_version_mapping(
        session=session,
        component_id=retriever_v2_version.component_id,
        release_stage=retriever_v2_version.release_stage,
        component_version_id=retriever_v2_version.id,
    )


def seed_rag_v4_parameter_groups(session: Session):
    parameter_groups = [
        db.ParameterGroup(
            id=RAG_V4_PARAMETER_GROUP_UUIDS["knowledge_parameters"],
            name="Knowledge Parameters",
        ),
        db.ParameterGroup(
            id=RAG_V4_PARAMETER_GROUP_UUIDS["advanced_knowledge_parameters"],
            name="Advanced Knowledge Parameters",
        ),
        db.ParameterGroup(
            id=RAG_V4_PARAMETER_GROUP_UUIDS["llm_parameters"],
            name="LLM Parameters",
        ),
        db.ParameterGroup(
            id=RAG_V4_PARAMETER_GROUP_UUIDS["advanced_llm_parameters"],
            name="Advanced LLM Parameters",
        ),
        db.ParameterGroup(
            id=RAG_V4_PARAMETER_GROUP_UUIDS["reranker_parameters"],
            name="Reranker Parameters",
        ),
        db.ParameterGroup(
            id=RAG_V4_PARAMETER_GROUP_UUIDS["vocabulary_search_parameters"],
            name="Vocabulary Search Parameters",
        ),
        db.ParameterGroup(
            id=RAG_V4_PARAMETER_GROUP_UUIDS["formatter_parameters"],
            name="Formatter Parameters",
        ),
    ]
    build_parameters_group(session, parameter_groups)

    component_parameter_groups = [
        db.ComponentParameterGroup(
            component_version_id=COMPONENT_VERSION_UUIDS["rag_agent_v4"],
            parameter_group_id=RAG_V4_PARAMETER_GROUP_UUIDS["knowledge_parameters"],
            group_order_within_component=1,
        ),
        db.ComponentParameterGroup(
            component_version_id=COMPONENT_VERSION_UUIDS["rag_agent_v4"],
            parameter_group_id=RAG_V4_PARAMETER_GROUP_UUIDS["advanced_knowledge_parameters"],
            group_order_within_component=2,
        ),
        db.ComponentParameterGroup(
            component_version_id=COMPONENT_VERSION_UUIDS["rag_agent_v4"],
            parameter_group_id=RAG_V4_PARAMETER_GROUP_UUIDS["llm_parameters"],
            group_order_within_component=3,
        ),
        db.ComponentParameterGroup(
            component_version_id=COMPONENT_VERSION_UUIDS["rag_agent_v4"],
            parameter_group_id=RAG_V4_PARAMETER_GROUP_UUIDS["advanced_llm_parameters"],
            group_order_within_component=4,
        ),
        db.ComponentParameterGroup(
            component_version_id=COMPONENT_VERSION_UUIDS["rag_agent_v4"],
            parameter_group_id=RAG_V4_PARAMETER_GROUP_UUIDS["reranker_parameters"],
            group_order_within_component=5,
        ),
        db.ComponentParameterGroup(
            component_version_id=COMPONENT_VERSION_UUIDS["rag_agent_v4"],
            parameter_group_id=RAG_V4_PARAMETER_GROUP_UUIDS["vocabulary_search_parameters"],
            group_order_within_component=6,
        ),
        db.ComponentParameterGroup(
            component_version_id=COMPONENT_VERSION_UUIDS["rag_agent_v4"],
            parameter_group_id=RAG_V4_PARAMETER_GROUP_UUIDS["formatter_parameters"],
            group_order_within_component=7,
        ),
    ]
    build_parameters_group_definitions(session, component_parameter_groups)

    parameter_group_assignments = {
        UUID("56f41bee-8473-415e-a1a5-6705b0af9fc0"): {  # data_source
            "parameter_group_id": RAG_V4_PARAMETER_GROUP_UUIDS["knowledge_parameters"],
            "parameter_order_within_group": 1,
        },
        UUID("84729d5d-4ee0-4f1e-abed-3b27283c8dc0"): {  # max_retrieved_chunks
            "parameter_group_id": RAG_V4_PARAMETER_GROUP_UUIDS["knowledge_parameters"],
            "parameter_order_within_group": 2,
        },
        UUID("452d5859-db93-43ce-a2b0-d072cd46e219"): {  # search_mode
            "parameter_group_id": RAG_V4_PARAMETER_GROUP_UUIDS["knowledge_parameters"],
            "parameter_order_within_group": 3,
        },
        UUID("4509b3b9-11df-4491-8441-e0c1bb23559b"): {  # enable_date_penalty_for_chunks
            "parameter_group_id": RAG_V4_PARAMETER_GROUP_UUIDS["advanced_knowledge_parameters"],
            "parameter_order_within_group": 1,
        },
        UUID("111d4a11-3722-4749-802e-dd1748dc050d"): {  # chunk_age_penalty_rate
            "parameter_group_id": RAG_V4_PARAMETER_GROUP_UUIDS["advanced_knowledge_parameters"],
            "parameter_order_within_group": 2,
        },
        UUID("fdc91df9-9e4b-44b3-be2a-c8ba236741cf"): {  # default_penalty_rate
            "parameter_group_id": RAG_V4_PARAMETER_GROUP_UUIDS["advanced_knowledge_parameters"],
            "parameter_order_within_group": 3,
        },
        UUID("66c18eb1-2653-465a-a435-8be8313f876c"): {  # metadata_date_key
            "parameter_group_id": RAG_V4_PARAMETER_GROUP_UUIDS["advanced_knowledge_parameters"],
            "parameter_order_within_group": 4,
        },
        UUID("8c9f7020-a65e-44da-a22e-0f6a19042dc0"): {  # max_retrieved_chunks_after_penalty
            "parameter_group_id": RAG_V4_PARAMETER_GROUP_UUIDS["advanced_knowledge_parameters"],
            "parameter_order_within_group": 5,
        },
        UUID("7af4208e-e8a0-46fc-87c7-34d3123afa11"): {  # completion_model
            "parameter_group_id": RAG_V4_PARAMETER_GROUP_UUIDS["llm_parameters"],
            "parameter_order_within_group": 1,
        },
        UUID("e446cd9c-56ac-4f91-8b52-ea6f4340ee25"): {  # prompt_template
            "parameter_group_id": RAG_V4_PARAMETER_GROUP_UUIDS["llm_parameters"],
            "parameter_order_within_group": 2,
        },
        UUID("b71a67b7-c634-4c02-b13e-707709fce859"): {  # temperature
            "parameter_group_id": RAG_V4_PARAMETER_GROUP_UUIDS["advanced_llm_parameters"],
            "parameter_order_within_group": 1,
        },
        UUID("01f50b86-bef8-462d-9a6d-1f993147e944"): {  # verbosity
            "parameter_group_id": RAG_V4_PARAMETER_GROUP_UUIDS["advanced_llm_parameters"],
            "parameter_order_within_group": 2,
        },
        UUID("7d035202-1639-4264-bab3-f5595748879d"): {  # reasoning
            "parameter_group_id": RAG_V4_PARAMETER_GROUP_UUIDS["advanced_llm_parameters"],
            "parameter_order_within_group": 3,
        },
        UUID("ad832572-d5f8-49f8-820a-5c9933aa04ab"): {  # api_key
            "parameter_group_id": RAG_V4_PARAMETER_GROUP_UUIDS["advanced_llm_parameters"],
            "parameter_order_within_group": 4,
        },
        UUID("bb2c46c1-7c19-4b77-a3ce-8d1cb9b504ba"): {  # use_reranker
            "parameter_group_id": RAG_V4_PARAMETER_GROUP_UUIDS["reranker_parameters"],
            "parameter_order_within_group": 1,
        },
        UUID("4aaa8fec-7a9a-4e04-a450-9d054699e7b7"): {  # cohere_model
            "parameter_group_id": RAG_V4_PARAMETER_GROUP_UUIDS["reranker_parameters"],
            "parameter_order_within_group": 2,
        },
        UUID("62788ddf-a40e-4e40-b332-47b689961805"): {  # score_threshold
            "parameter_group_id": RAG_V4_PARAMETER_GROUP_UUIDS["reranker_parameters"],
            "parameter_order_within_group": 3,
        },
        UUID("e3489939-50e6-48f4-8806-08e7761669f2"): {  # num_doc_reranked
            "parameter_group_id": RAG_V4_PARAMETER_GROUP_UUIDS["reranker_parameters"],
            "parameter_order_within_group": 4,
        },
        UUID("0bba7a67-c271-4558-b3ba-44ddbd536b0b"): {  # use_vocabulary_search
            "parameter_group_id": RAG_V4_PARAMETER_GROUP_UUIDS["vocabulary_search_parameters"],
            "parameter_order_within_group": 1,
        },
        UUID("7dd95b0c-f539-48b8-9c52-f96f32a781b9"): {  # vocabulary_context_data
            "parameter_group_id": RAG_V4_PARAMETER_GROUP_UUIDS["vocabulary_search_parameters"],
            "parameter_order_within_group": 2,
        },
        UUID("409e7c43-8d73-48d6-b66f-b0506af915e7"): {  # fuzzy_threshold
            "parameter_group_id": RAG_V4_PARAMETER_GROUP_UUIDS["vocabulary_search_parameters"],
            "parameter_order_within_group": 3,
        },
        UUID("22c922fb-b917-4c1c-9bd4-f8f838e37a49"): {  # fuzzy_matching_candidates
            "parameter_group_id": RAG_V4_PARAMETER_GROUP_UUIDS["vocabulary_search_parameters"],
            "parameter_order_within_group": 4,
        },
        UUID("bb5c1ec8-aafa-46e0-9d83-97af786eadda"): {  # vocabulary_context_prompt_key
            "parameter_group_id": RAG_V4_PARAMETER_GROUP_UUIDS["vocabulary_search_parameters"],
            "parameter_order_within_group": 5,
        },
        UUID("75959c9f-c748-4503-9f94-44fd23116260"): {  # use_formatter
            "parameter_group_id": RAG_V4_PARAMETER_GROUP_UUIDS["formatter_parameters"],
            "parameter_order_within_group": 1,
        },
        UUID("026c2ca1-f702-43f2-a530-e485a80dbd9c"): {  # add_sources
            "parameter_group_id": RAG_V4_PARAMETER_GROUP_UUIDS["formatter_parameters"],
            "parameter_order_within_group": 2,
        },
    }
    build_components_parameters_assignments_to_parameter_groups(session, parameter_group_assignments)
