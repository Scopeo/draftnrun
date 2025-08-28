from uuid import UUID
import json

from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.models import (
    ParameterType,
    UIComponent,
    UIComponentProperties,
    SelectOption,
)
from ada_backend.database.component_definition_seeding import (
    upsert_component_categories,
    upsert_components,
    upsert_components_parameter_child_relationships,
    upsert_components_parameter_definitions,
)
from ada_backend.database.seed.seed_categories import CATEGORY_UUIDS
from ada_backend.database.seed.seed_tool_description import TOOL_DESCRIPTION_UUIDS
from ada_backend.database.seed.utils import (
    COMPONENT_UUIDS,
    ParameterLLMConfig,
    build_completion_service_config_definitions,
)
from ada_backend.services.registry import COMPLETION_MODEL_IN_DB
from engine.agent.synthesizer_prompts import (
    get_base_synthetizer_prompt_template,
    get_hybrid_synthetizer_prompt_template,
)


def seed_rag_components(session: Session):
    synthesizer = db.Component(
        id=COMPONENT_UUIDS["synthesizer"],
        name="Synthesizer",
        description="Synthesizer for generating outputs",
        release_stage=db.ReleaseStage.PUBLIC,
    )
    hybrid_synthesizer = db.Component(
        id=COMPONENT_UUIDS["hybrid_synthesizer"],
        name="HybridSynthesizer",
        description="Hybrid Synthesizer for generating outputs",
        release_stage=db.ReleaseStage.BETA,
    )
    chunk_selector = db.Component(
        id=COMPONENT_UUIDS["relevant_chunk_selector"],
        name="ChunkSelector",
        description="Chunk Selector for selecting relevant chunks",
        release_stage=db.ReleaseStage.BETA,
    )
    retriever = db.Component(
        id=COMPONENT_UUIDS["retriever"],
        name="Retriever",
        description="Retriever for fetching chunks",
        release_stage=db.ReleaseStage.PUBLIC,
    )
    cohere_reranker = db.Component(
        id=COMPONENT_UUIDS["cohere_reranker"],
        name="CohereReranker",
        description="Cohere API-based Reranker",
        release_stage=db.ReleaseStage.PUBLIC,
    )
    rag_formatter = db.Component(
        id=COMPONENT_UUIDS["formatter"],
        name="Formatter",
        description="Rag formatter. Design to customize how to display sources on answer",
        release_stage=db.ReleaseStage.PUBLIC,
    )
    vocabulary_search = db.Component(
        id=COMPONENT_UUIDS["vocabulary_search"],
        name="Vocabulary Search",
        description="Enriches RAG with search on user defined vocabulary",
        release_stage=db.ReleaseStage.PUBLIC,
    )
    upsert_components(
        session=session,
        components=[
            synthesizer,
            hybrid_synthesizer,
            chunk_selector,
            retriever,
            cohere_reranker,
            rag_formatter,
            vocabulary_search,
        ],
    )

    rag_agent = db.Component(
        id=COMPONENT_UUIDS["rag_agent"],
        name="RAG",
        description="Retrieves information from knowledge bases using RAG",
        is_agent=True,
        function_callable=True,
        release_stage=db.ReleaseStage.PUBLIC,
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["default_rag_tool_description"],
    )
    hybrid_rag_agent = db.Component(
        id=COMPONENT_UUIDS["hybrid_rag_agent"],
        name="HybridRAGAgent",
        description="Hybrid RAG Agent",
        is_agent=False,
        function_callable=False,
        release_stage=db.ReleaseStage.BETA,
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["default_rag_tool_description"],
    )
    upsert_components(
        session=session,
        components=[
            rag_agent,
            hybrid_rag_agent,
        ],
    )

    # RAG
    rag_reranker_param = db.ComponentParameterDefinition(
        id=UUID("4f234948-c276-4f3f-88d1-cc8df58fc20e"),
        component_id=rag_agent.id,
        name="reranker",
        type=ParameterType.COMPONENT,
        nullable=True,
    )
    rag_formatter_param = db.ComponentParameterDefinition(
        id=UUID("c5e9b6da-4b49-455f-8cf9-cb4f9f2e4468"),
        component_id=rag_agent.id,
        name="formatter",
        type=ParameterType.COMPONENT,
        nullable=True,
    )
    rag_vocabulary_search_param = db.ComponentParameterDefinition(
        id=UUID("8e6c5827-667e-4c01-bf8b-e82a65614c5a"),
        component_id=rag_agent.id,
        name="vocabulary_search",
        type=ParameterType.COMPONENT,
        nullable=True,
    )
    upsert_components_parameter_definitions(
        session=session,
        component_parameter_definitions=[
            rag_reranker_param,
            rag_formatter_param,
            rag_vocabulary_search_param,
        ],
    )
    upsert_components_parameter_child_relationships(
        session=session,
        component_parameter_child_relationships=[
            db.ComponentParameterChildRelationship(
                id=UUID("b314a46c-62f0-4d0a-b56f-2d4fa43fa242"),
                component_parameter_definition_id=rag_reranker_param.id,
                child_component_id=cohere_reranker.id,
            ),
            db.ComponentParameterChildRelationship(
                id=UUID("8a38709b-3a3a-4ae3-b1d5-0dc244a3280c"),
                component_parameter_definition_id=rag_formatter_param.id,
                child_component_id=rag_formatter.id,
            ),
            db.ComponentParameterChildRelationship(
                id=UUID("004062a7-724a-4f4e-b49d-b56681bd85ab"),
                component_parameter_definition_id=rag_vocabulary_search_param.id,
                child_component_id=vocabulary_search.id,
            ),
        ],
    )

    upsert_component_categories(session=session, component_id=rag_agent.id, category_ids=[CATEGORY_UUIDS["query"]])
    # Hybrid RAG
    hybrid_rag_retriever_param = db.ComponentParameterDefinition(
        id=UUID("7d4bb3fd-9188-4b40-82de-bb85c7e8f08a"),
        component_id=hybrid_rag_agent.id,
        name="retriever",
        type=ParameterType.COMPONENT,
        nullable=True,
    )
    hybrid_rag_synthesizer_param = db.ComponentParameterDefinition(
        id=UUID("7e91d7a2-8bde-4f67-b4b3-4b4b9b3c406c"),
        component_id=hybrid_rag_agent.id,
        name="synthesizer",
        type=ParameterType.COMPONENT,
        nullable=False,
    )
    hybrid_rag_reranker_param = db.ComponentParameterDefinition(
        id=UUID("370fa33e-bb78-47fc-a09d-1e149fe593e0"),
        component_id=hybrid_rag_agent.id,
        name="reranker",
        type=ParameterType.COMPONENT,
        nullable=True,
    )
    hybrid_rag_hybrid_synthesizer_param = db.ComponentParameterDefinition(
        id=UUID("85cf3541-b7b8-4f58-815e-3c8f60e5109b"),
        component_id=hybrid_rag_agent.id,
        name="hybrid_synthesizer",
        type=ParameterType.COMPONENT,
        nullable=False,
    )
    hybrid_rag_relevant_chunk_selector_param = db.ComponentParameterDefinition(
        id=UUID("fef295ec-51cc-4ac5-9f09-c78f77f3ea07"),
        component_id=hybrid_rag_agent.id,
        name="relevant_chunk_selector",
        type=ParameterType.COMPONENT,
        nullable=False,
    )
    hybrid_rag_formatter_param = db.ComponentParameterDefinition(
        id=UUID("7cf4fc67-d2d8-49a5-bc93-8e9f5888933c"),
        component_id=hybrid_rag_agent.id,
        name="formatter",
        type=ParameterType.COMPONENT,
        nullable=True,
    )
    upsert_components_parameter_definitions(
        session=session,
        component_parameter_definitions=[
            hybrid_rag_retriever_param,
            hybrid_rag_synthesizer_param,
            hybrid_rag_reranker_param,
            hybrid_rag_hybrid_synthesizer_param,
            hybrid_rag_relevant_chunk_selector_param,
            hybrid_rag_formatter_param,
        ],
    )
    upsert_components_parameter_child_relationships(
        session=session,
        component_parameter_child_relationships=[
            db.ComponentParameterChildRelationship(
                id=UUID("60e0df9d-f80f-4b58-8c91-9bdf5cd88e8c"),
                component_parameter_definition_id=hybrid_rag_retriever_param.id,
                child_component_id=retriever.id,
            ),
            db.ComponentParameterChildRelationship(
                id=UUID("4ad3cdd2-790c-4f91-83f1-2f0e4e5272ff"),
                component_parameter_definition_id=hybrid_rag_synthesizer_param.id,
                child_component_id=synthesizer.id,
            ),
            db.ComponentParameterChildRelationship(
                id=UUID("b899f694-e2b4-4636-986f-dbd0ad0c17c6"),
                component_parameter_definition_id=hybrid_rag_reranker_param.id,
                child_component_id=cohere_reranker.id,
            ),
            db.ComponentParameterChildRelationship(
                id=UUID("285f3e6c-0557-4ab7-bf9b-b1d645ab81b1"),
                component_parameter_definition_id=hybrid_rag_hybrid_synthesizer_param.id,
                child_component_id=hybrid_synthesizer.id,
            ),
            db.ComponentParameterChildRelationship(
                id=UUID("29c64935-442a-495f-88e1-924028370118"),
                component_parameter_definition_id=hybrid_rag_relevant_chunk_selector_param.id,
                child_component_id=chunk_selector.id,
            ),
            db.ComponentParameterChildRelationship(
                id=UUID("61b56c07-3f5c-42b7-b34a-53eec9c51f2d"),
                component_parameter_definition_id=hybrid_rag_formatter_param.id,
                child_component_id=rag_formatter.id,
            ),
        ],
    )

    # Retriever
    retriever_collection_name_param = db.ComponentParameterDefinition(
        id=UUID("2caba92f-421b-43a4-a197-9b53d9da79be"),
        component_id=retriever.id,
        name="data_source",
        type=ParameterType.DATA_SOURCE,
        nullable=False,
        ui_component=UIComponent.SELECT,
        ui_component_properties=UIComponentProperties(
            label="Data Source", description="The data source from which to retrieve chunks. "
        ).model_dump(exclude_unset=True, exclude_none=True),
        is_advanced=False,
    )
    retriever_max_retrieved_chunks_param = db.ComponentParameterDefinition(
        id=UUID("2799c83e-2df0-4b55-babb-86f84e4f2ce1"),
        component_id=retriever.id,
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
        is_advanced=True,
    )
    retriever_enable_date_penalty_for_chunks_param = db.ComponentParameterDefinition(
        id=UUID("f3b0a2c4-1d5e-4b8e-8c7f-6a2d9f3e1b2d"),
        component_id=retriever.id,
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
    )
    retriever_chunk_age_penalty_rate_param = db.ComponentParameterDefinition(
        id=UUID("d2f3a2c4-1d5e-4b8e-8c7f-6a2d9f3e1b2d"),
        component_id=retriever.id,
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
    retriever_default_penalty_rate_param = db.ComponentParameterDefinition(
        id=UUID("d94c8c4e-2f89-4b9b-9738-74c2b90801a5"),
        component_id=retriever.id,
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

    retriever_metadata_date_key_param = db.ComponentParameterDefinition(
        id=UUID("c2fa6342-0c9f-4b77-b0b2-2bb18a77a6c5"),
        component_id=retriever.id,
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
    retriever_max_retrieved_chunks_after_penalty_param = db.ComponentParameterDefinition(
        id=UUID("fc3e8e2b-2f5f-4b61-9aef-5480d7ed22f1"),
        component_id=retriever.id,
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
    )

    upsert_components_parameter_definitions(
        session=session,
        component_parameter_definitions=[
            retriever_collection_name_param,
            retriever_max_retrieved_chunks_param,
            retriever_enable_date_penalty_for_chunks_param,
            retriever_chunk_age_penalty_rate_param,
            retriever_default_penalty_rate_param,
            retriever_metadata_date_key_param,
            retriever_max_retrieved_chunks_after_penalty_param,
        ],
    )

    upsert_components_parameter_definitions(
        session=session,
        component_parameter_definitions=[
            # RAG Agent
            db.ComponentParameterDefinition(
                id=UUID("c5c813b4-884c-42af-9303-d56189e57f48"),
                component_id=rag_agent.id,
                name="input_data_field_for_messages_history",
                type=ParameterType.STRING,
                nullable=False,
                default="messages",
                ui_component=UIComponent.TEXTFIELD,
                ui_component_properties=UIComponentProperties(
                    label="Messages history key from input",
                    placeholder="Enter the key from your input data to access messages history",
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=True,
            ),
            # RAG-level Synthesizer configuration
            db.ComponentParameterDefinition(
                id=UUID("f78a5a64-6c8e-4f80-8d9d-3db3d6f2d5a0"),
                component_id=rag_agent.id,
                name="prompt_template",
                type=ParameterType.STRING,
                nullable=True,
                default=get_base_synthetizer_prompt_template(),
                ui_component=UIComponent.TEXTAREA,
                ui_component_properties=UIComponentProperties(
                    label="Prompt Template",
                    placeholder=(
                        "Enter your prompt template here. "
                        "Use {context_str} and {query_str} for variable substitution."
                    ),
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=False,
            ),
            # RAG-level Retriever configuration
            db.ComponentParameterDefinition(
                id=UUID("a2b9b94d-9f40-4f0a-9c9b-6c3c7a9b3d8e"),
                component_id=rag_agent.id,
                name="data_source",
                type=ParameterType.DATA_SOURCE,
                nullable=False,
                ui_component=UIComponent.SELECT,
                ui_component_properties=UIComponentProperties(
                    label="Data Source",
                    description="The data source from which to retrieve chunks. ",
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=False,
            ),
            db.ComponentParameterDefinition(
                id=UUID("f2f8d3c2-4a1e-4f61-8c9b-2e7c1a8d9f21"),
                component_id=rag_agent.id,
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
                is_advanced=True,
            ),
            db.ComponentParameterDefinition(
                id=UUID("e3c7d2b1-5f6a-4c3e-9b7a-1c2d3e4f5a6b"),
                component_id=rag_agent.id,
                name="enable_date_penalty_for_chunks",
                type=ParameterType.BOOLEAN,
                nullable=True,
                default="False",
                ui_component=UIComponent.CHECKBOX,
                ui_component_properties=UIComponentProperties(
                    label="Apply age based penalty",
                    description="When enabled, older content chunks will be penalized based on their age. This helps prioritize more recent content.",
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=True,
            ),
            db.ComponentParameterDefinition(
                id=UUID("b1a2c3d4-e5f6-41a2-93b7-2c1d4e5f6a7b"),
                component_id=rag_agent.id,
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
                    description="Determines how much to penalize older content chunks. A higher value means older chunks are penalized more.",
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=True,
            ),
            db.ComponentParameterDefinition(
                id=UUID("c4d5e6f7-a8b9-4c1d-82e3-4f5a6b7c8d9e"),
                component_id=rag_agent.id,
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
                    description="Used as a fallback penalty rate for chunks without a specific date. This allows you to decide how to deal with missing information.",
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=True,
            ),
            db.ComponentParameterDefinition(
                id=UUID("d6e7f8a9-b0c1-4d2e-93f4-5a6b7c8d9e0f"),
                component_id=rag_agent.id,
                name="metadata_date_key",
                type=ParameterType.STRING,
                nullable=True,
                default="date",
                ui_component=UIComponent.TEXTFIELD,
                ui_component_properties=UIComponentProperties(
                    label="Date field used for penalty",
                    description=(
                        "The metadata field(s) that contain the date information for each chunk. "
                        "You can specify multiple date fields names as a comma-separated list (e.g., created_date,updated_date). "
                        "The system will check each field in order and use the first valid (non-null) date it finds. "
                        "This date is used to calculate the chunk's age when applying penalties."
                    ),
                    placeholder="Enter the date field here",
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=True,
            ),
            db.ComponentParameterDefinition(
                id=UUID("e0f9a8b7-c6d5-4e3f-91a2-3b4c5d6e7f8a"),
                component_id=rag_agent.id,
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
                        "Note: this value should be less than or equal to the maximum number of retrieved chunks before penalty."
                    ),
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=True,
            ),
            # Completion service config for Synthesizer at RAG level
            *build_completion_service_config_definitions(
                component_id=rag_agent.id,
                params_to_seed=[
                    ParameterLLMConfig(
                        param_name=COMPLETION_MODEL_IN_DB,
                        param_id=UUID("a4c6e8f0-1b2c-4d3e-9f5a-6b7c8d9e0f1a"),
                    ),
                    ParameterLLMConfig(
                        param_name="api_key",
                        param_id=UUID("b5d7f9e1-2c3d-4e5f-8a9b-7c8d9e0f1a2b"),
                    ),
                ],
            ),
            # Vocabulary Search
            db.ComponentParameterDefinition(
                id=UUID("4f207c2b-4231-4fc0-bf2b-51a39a3ae666"),
                component_id=vocabulary_search.id,
                name="vocabulary_context_data",
                type=ParameterType.JSON,
                nullable=False,
                default=json.dumps({}),
                ui_component=UIComponent.TEXTAREA,
                ui_component_properties=UIComponentProperties(
                    label="The Glossary you want to use to enrich the RAG agent's context",
                    placeholder="""Put a correct formatted
                    json {'term' : ['term1', 'term2', 'term3'],
                    'definition' : ['definition1', 'definition2', 'definition3']}""",
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=False,
            ),
            db.ComponentParameterDefinition(
                id=UUID("3b7d03ce-3054-4248-8c6f-be76973ce58d"),
                component_id=vocabulary_search.id,
                name="fuzzy_matching_candidates",
                type=ParameterType.INTEGER,
                nullable=False,
                default=10,
                ui_component=UIComponent.SLIDER,
                ui_component_properties=UIComponentProperties(
                    min=1, max=100, step=1, marks=True, label="Number of definitions to retrieve"
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=False,
            ),
            db.ComponentParameterDefinition(
                id=UUID("14b0d5ce-326c-402a-8678-bd21d49abdf3"),
                component_id=vocabulary_search.id,
                name="fuzzy_threshold",
                type=ParameterType.INTEGER,
                nullable=False,
                default=90,
                ui_component=UIComponent.SLIDER,
                ui_component_properties=UIComponentProperties(
                    min=1,
                    max=100,
                    step=1,
                    marks=True,
                    label="Fuzzy Matching Threshold to retrieve vocabulary",
                    description=(
                        "Fuzzy matching is a technique used to find approximate matches between strings. "
                        "It handles typos, misspellings, and variations in wording. "
                        "The fuzzy matching here will try to find the vocabulary terms in the query of the user. "
                        "A thresold of 100 mean that the term is exactly the same in the query. "
                        "When lowering, you allow mistakes (misspelling, plural etc). "
                    ),
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=False,
            ),
            db.ComponentParameterDefinition(
                id=UUID("80ae22be-5832-4c7b-a936-6d129caeec80"),
                component_id=vocabulary_search.id,
                name="vocabulary_context_prompt_key",
                type=ParameterType.STRING,
                nullable=False,
                default="retrieved_definitions",
                ui_component=UIComponent.TEXTFIELD,
                ui_component_properties=UIComponentProperties(
                    label="Prompt key for vocabulary context injection",
                    description="Put {retrieved_definitions} in the Synthesizer prompt of your RAG to allow the "
                    "injection of retrieved definitions from your Glossary into the Synthesizer prompt "
                    "during a RAG call. This will allow the RAG to answer using your collection "
                    "and Glossary.",
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=False,
            ),
            # RAG Formatter
            db.ComponentParameterDefinition(
                id=UUID("b3f71f3a-8e3d-4622-9ef1-723a427b4f74"),
                component_id=rag_formatter.id,
                name="add_sources",
                type=ParameterType.BOOLEAN,
                nullable=True,
                default="False",
            ),
            # Cohere Reranker
            db.ComponentParameterDefinition(
                id=UUID("3cc26c73-f803-4726-aea7-4d4602f47a5e"),
                component_id=cohere_reranker.id,
                name="cohere_model",
                type=ParameterType.STRING,
                nullable=True,
                default="rerank-multilingual-v3.0",
                ui_component=UIComponent.SELECT,
                ui_component_properties=UIComponentProperties(
                    options=[
                        # Cohere
                        SelectOption(value="rerank-v3.5", label="Rerank v3.5"),
                        SelectOption(value="rerank-multilingual-v3.0", label="Rerank Multilingual v3.0"),
                    ],
                    label="Cohere Model",
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=True,
            ),
            db.ComponentParameterDefinition(
                id=UUID("9cf01671-1cf7-4a34-9f64-df92a3e0193f"),
                component_id=cohere_reranker.id,
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
                id=UUID("9b474d7b-6c0b-45d0-b6b4-ccefd6931d0b"),
                component_id=cohere_reranker.id,
                name="num_doc_reranked",
                type=ParameterType.INTEGER,
                nullable=True,
                default="5",
                ui_component=UIComponent.SLIDER,
                ui_component_properties=UIComponentProperties(
                    min=1, max=10, step=1, marks=True, label="Number of Documents Reranked"
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=False,
            ),
            # Synthesizer
            db.ComponentParameterDefinition(
                id=UUID("373dc6d2-e12d-495c-936f-e07d1c27e254"),
                component_id=synthesizer.id,
                name="prompt_template",
                type=ParameterType.STRING,
                nullable=True,
                default=get_base_synthetizer_prompt_template(),
                ui_component=UIComponent.TEXTAREA,
                ui_component_properties=UIComponentProperties(
                    label="Prompt Template",
                    placeholder=(
                        "Enter your prompt template here. "
                        "Use {context_str} and {query_str} for variable substitution."
                    ),
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=False,
            ),
            *build_completion_service_config_definitions(
                component_id=synthesizer.id,
                params_to_seed=[
                    ParameterLLMConfig(
                        param_name=COMPLETION_MODEL_IN_DB,
                        param_id=UUID("8d4a2304-55f9-4b94-9206-67f56a6ac750"),
                    ),
                    ParameterLLMConfig(
                        param_name="api_key",
                        param_id=UUID("989b3cec-7f01-4098-847b-a6ad7c07af24"),
                    ),
                ],
            ),
            # Hybrid Synthesizer
            db.ComponentParameterDefinition(
                id=UUID("78df9f84-2d9c-4499-bafe-24c7c96d2a08"),
                component_id=hybrid_synthesizer.id,
                name="prompt_template",
                type=ParameterType.STRING,
                nullable=True,
                default=get_hybrid_synthetizer_prompt_template(),
                ui_component=UIComponent.TEXTAREA,
                ui_component_properties=UIComponentProperties(
                    label="Prompt Template",
                    placeholder=(
                        "Enter your prompt template here. "
                        "Use {context_str} and {query_str} for variable substitution."
                    ),
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=False,
            ),
            *build_completion_service_config_definitions(
                component_id=hybrid_synthesizer.id,
                params_to_seed=[
                    ParameterLLMConfig(
                        param_name=COMPLETION_MODEL_IN_DB,
                        param_id=UUID("7c5d0eae-d865-430e-a6d0-b8f4060a6b23"),
                    ),
                    ParameterLLMConfig(
                        param_name="api_key",
                        param_id=UUID("3703e3a4-bd6d-4aea-b8d3-9196c11f9727"),
                    ),
                ],
            ),
            # Chunk Selector
            db.ComponentParameterDefinition(
                id=UUID("3b738fb6-3a3f-4261-9b7e-78a3256d4db2"),
                component_id=chunk_selector.id,
                name="prompt_template",
                type=ParameterType.STRING,
                nullable=True,
                ui_component=UIComponent.TEXTAREA,
                ui_component_properties=UIComponentProperties(
                    label="Prompt Template",
                    placeholder="Enter your prompt template here. Use {input} for variable substitution.",
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=False,
            ),
            *build_completion_service_config_definitions(
                component_id=chunk_selector.id,
                params_to_seed=[
                    ParameterLLMConfig(
                        param_name=COMPLETION_MODEL_IN_DB,
                        param_id=UUID("3be1a99a-29c4-4ff1-bef0-63122f786c61"),
                    ),
                    ParameterLLMConfig(
                        param_name="api_key",
                        param_id=UUID("7fc840a0-fdb4-4582-bf5d-c9b0d4af0ef1"),
                    ),
                ],
            ),
        ],
    )
