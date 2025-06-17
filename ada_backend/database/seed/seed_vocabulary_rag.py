from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.models import (
    ParameterType,
    UIComponent,
    UIComponentProperties,
    SelectOption,
)
from ada_backend.database.component_definition_seeding import (
    upsert_components,
    upsert_components_parameter_child_relationships,
    upsert_components_parameter_definitions,
)
from ada_backend.database.seed.seed_tool_description import TOOL_DESCRIPTION_UUIDS
from ada_backend.database.seed.utils import COMPONENT_UUIDS, ParameterLLMConfig, build_llm_config_definitions
from ada_backend.services.registry import PARAM_MODEL_NAME_IN_DB
from engine.agent.synthesizer_prompts import get_vocabulary_synthesizer_prompt_template


def seed_vocabulary_rag_components(session: Session):
    vocabulary_enhanced_synthesizer = db.Component(
        id=COMPONENT_UUIDS["vocabulary_enhanced_synthesizer"],
        name="VocabularyEnhancedSynthesizer",
        description="Synthesizer for generating outputs",
        release_stage=db.ReleaseStage.INTERNAL,
    )
    vocabulary_search = db.Component(
        id=COMPONENT_UUIDS["vocabulary_search"],
        name="VocabularySearch",
        description="Retriever for fetching chunks",
        release_stage=db.ReleaseStage.INTERNAL,
    )
    upsert_components(
        session=session,
        components=[
            vocabulary_enhanced_synthesizer,
            vocabulary_search,
        ],
    )
    vocabulary_enhanced_rag_agent = db.Component(
        id=COMPONENT_UUIDS["vocabulary_enhanced_rag_agent"],
        name="VocabularyEnhancedRAGAgent",
        description="Get information from knowledge bases and vocabulary",
        is_agent=False,
        function_callable=False,
        release_stage=db.ReleaseStage.INTERNAL,
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["default_rag_tool_description"],
    )
    upsert_components(
        session=session,
        components=[
            vocabulary_enhanced_rag_agent,
        ],
    )
    # Vocabulary Enhanced RAG
    vocab_rag_retriever_param = db.ComponentParameterDefinition(
        id=UUID("3a29fbb1-53f0-44c6-b1e1-d5a2d93f5b0a"),
        component_id=vocabulary_enhanced_rag_agent.id,
        name="retriever",
        type=ParameterType.COMPONENT,
        nullable=False,
    )
    vocab_rag_vocabulary_search_param = db.ComponentParameterDefinition(
        id=UUID("9f0c4ab7-621c-46cf-921b-260f5890cc3f"),
        component_id=vocabulary_enhanced_rag_agent.id,
        name="vocabulary_search",
        type=ParameterType.COMPONENT,
        nullable=False,
    )
    vocab_rag_synthesizer_param = db.ComponentParameterDefinition(
        id=UUID("32a40716-30c4-4d6e-82ff-0be6eecf5951"),
        component_id=vocabulary_enhanced_rag_agent.id,
        name="synthesizer",
        type=ParameterType.COMPONENT,
        nullable=False,
    )
    vocab_rag_reranker_param = db.ComponentParameterDefinition(
        id=UUID("9502a8a6-f48b-42cc-a3f0-c6df296a1677"),
        component_id=vocabulary_enhanced_rag_agent.id,
        name="reranker",
        type=ParameterType.COMPONENT,
        nullable=True,
    )
    vocab_rag_formatter_param = db.ComponentParameterDefinition(
        id=UUID("2e05bc76-54d0-4f45-86b5-50bcbb301c9e"),
        component_id=vocabulary_enhanced_rag_agent.id,
        name="formatter",
        type=ParameterType.COMPONENT,
        nullable=True,
    )
    upsert_components_parameter_definitions(
        session=session,
        component_parameter_definitions=[
            vocab_rag_retriever_param,
            vocab_rag_vocabulary_search_param,
            vocab_rag_synthesizer_param,
            vocab_rag_reranker_param,
            vocab_rag_formatter_param,
        ],
    )

    upsert_components_parameter_child_relationships(
        session=session,
        component_parameter_child_relationships=[
            db.ComponentParameterChildRelationship(
                id=UUID("1e7c4fc5-3e58-4f0a-a3f7-5981aaae7c37"),
                component_parameter_definition_id=vocab_rag_retriever_param.id,
                child_component_id=COMPONENT_UUIDS["retriever"],
            ),
            db.ComponentParameterChildRelationship(
                id=UUID("3d2f4a8c-d98e-48d8-b315-6df1762c556f"),
                component_parameter_definition_id=vocab_rag_vocabulary_search_param.id,
                child_component_id=vocabulary_search.id,
            ),
            db.ComponentParameterChildRelationship(
                id=UUID("9c9dbb74-3008-49cf-a6d6-03293ff83577"),
                component_parameter_definition_id=vocab_rag_synthesizer_param.id,
                child_component_id=vocabulary_enhanced_synthesizer.id,
            ),
            db.ComponentParameterChildRelationship(
                id=UUID("6c1f64aa-ff0e-4a82-b86a-f80321a580ff"),
                component_parameter_definition_id=vocab_rag_reranker_param.id,
                child_component_id=COMPONENT_UUIDS["cohere_reranker"],
            ),
            db.ComponentParameterChildRelationship(
                id=UUID("14f50ab4-49d4-4b02-999e-2591888a8454"),
                component_parameter_definition_id=vocab_rag_formatter_param.id,
                child_component_id=COMPONENT_UUIDS["formatter"],
            ),
        ],
    )

    # Vocab Search
    vocab_search_db_service_param = db.ComponentParameterDefinition(
        id=UUID("1074ae9c-1944-4f0f-b9e8-2b27a59b6e2a"),
        component_id=vocabulary_search.id,
        name="db_service",
        type=ParameterType.COMPONENT,
        nullable=False,
    )
    upsert_components_parameter_definitions(
        session=session, component_parameter_definitions=[vocab_search_db_service_param]
    )
    upsert_components_parameter_child_relationships(
        session=session,
        component_parameter_child_relationships=[
            db.ComponentParameterChildRelationship(
                id=UUID("0da14d9b-d699-4542-974f-dc57e15f248f"),
                component_parameter_definition_id=vocab_search_db_service_param.id,
                child_component_id=COMPONENT_UUIDS["snowflake_db_service"],
            )
        ],
    )
    upsert_components_parameter_definitions(
        session=session,
        component_parameter_definitions=[  # Vocabulary RAG agent
            db.ComponentParameterDefinition(
                id=UUID("d73052c1-82d5-4ad3-b8e7-cccf8e8a3804"),
                component_id=vocabulary_enhanced_rag_agent.id,
                name="filtering_condition",
                type=ParameterType.STRING,
                nullable=True,
                default="OR",
                ui_component=UIComponent.SELECT,
                ui_component_properties=UIComponentProperties(
                    options=[SelectOption(value="OR", label="OR"), SelectOption(value="AND", label="AND")],
                    label="Filtering Condition",
                ).model_dump(exclude_unset=True, exclude_none=True),
            ),
            db.ComponentParameterDefinition(
                id=UUID("9472f57b-8d8f-4c8f-8ee1-81c94fc9726d"),
                component_id=COMPONENT_UUIDS["formatter"],
                name="add_sources",
                type=ParameterType.BOOLEAN,
                nullable=True,
                default="False",
                ui_component=UIComponent.CHECKBOX,
                ui_component_properties=UIComponentProperties(label="Add Sources").model_dump(
                    exclude_unset=True, exclude_none=True
                ),
                is_advanced=False,
            ),
            # Vocabulary Synthesizer
            db.ComponentParameterDefinition(
                id=UUID("67be6c2e-8023-4e2d-9203-c234f5ebd947"),
                component_id=vocabulary_enhanced_synthesizer.id,
                name="prompt_template",
                type=ParameterType.STRING,
                nullable=True,
                default=get_vocabulary_synthesizer_prompt_template(),
                ui_component=UIComponent.TEXTAREA,
                ui_component_properties=UIComponentProperties(
                    label="Prompt Template",
                    placeholder=(
                        "Enter your prompt template here. "
                        "Use {vocabulary_context_str}, {context_str} and {query_str} for variable substitution."
                    ),
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=False,
            ),
            *build_llm_config_definitions(
                component_id=vocabulary_enhanced_synthesizer.id,
                params_to_seed=[
                    ParameterLLMConfig(
                        param_name=PARAM_MODEL_NAME_IN_DB,
                        param_id=UUID("7e28e4dc-b377-4cd5-a9ec-81e2b2187ab9"),
                    ),
                    ParameterLLMConfig(
                        param_name="default_temperature",
                        param_id=UUID("52cf3a13-4fcb-4c19-b89a-bd2a016e2ee7"),
                    ),
                    ParameterLLMConfig(
                        param_name="api_key",
                        param_id=UUID("3442d221-e6f8-4fa3-b542-24969881fdaf"),
                    ),
                ],
            ),
            # Vocabulary Retriever
            db.ComponentParameterDefinition(
                id=UUID("87f71635-5fa4-4f8f-a1d1-5f33c97fba62"),
                component_id=vocabulary_search.id,
                name="fuzzy_threshold",
                type=ParameterType.INTEGER,
                nullable=False,
                default="80",
                ui_component=UIComponent.SLIDER,
                ui_component_properties=UIComponentProperties(
                    min=1, max=100, step=1, marks=True, label="Thresold to pass fuzzy matching"
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=True,
            ),
            db.ComponentParameterDefinition(
                id=UUID("e2c19387-e5c7-486b-baa8-e3ad20e1f6c8"),
                component_id=vocabulary_search.id,
                name="fuzzy_matching_candidates",
                type=ParameterType.INTEGER,
                nullable=False,
                default="10",
                ui_component=UIComponent.SLIDER,
                ui_component_properties=UIComponentProperties(
                    min=1, max=50, step=1, marks=True, label="Maximum Retrieved vocabulary terms"
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=True,
            ),
            db.ComponentParameterDefinition(
                id=UUID("9e55d3e5-316f-4ad2-bde5-7e46e48bc2a6"),
                component_id=vocabulary_search.id,
                name="table_name",
                type=ParameterType.STRING,
                nullable=False,
                ui_component=UIComponent.TEXTFIELD,
                ui_component_properties=UIComponentProperties(
                    label="Table Name",
                    placeholder="Enter the table name here for your vocabulary",
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=False,
            ),
            db.ComponentParameterDefinition(
                id=UUID("93b4f0e5-872a-47f8-902f-e29e1d7d8d09"),
                component_id=vocabulary_search.id,
                name="schema_name",
                type=ParameterType.STRING,
                nullable=False,
                ui_component=UIComponent.TEXTFIELD,
                ui_component_properties=UIComponentProperties(
                    label="Schema Name",
                    placeholder="Enter the schema name to access your vocabulary table in the db",
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=False,
            ),
        ],
    )
