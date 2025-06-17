from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.models import (
    ParameterType,
    UIComponent,
    UIComponentProperties,
)
from ada_backend.database.component_definition_seeding import (
    upsert_components,
    upsert_components_parameter_child_relationships,
    upsert_components_parameter_definitions,
)
from ada_backend.database.seed.seed_tool_description import TOOL_DESCRIPTION_UUIDS
from ada_backend.database.seed.utils import COMPONENT_UUIDS, ParameterLLMConfig, build_llm_config_definitions
from ada_backend.services.registry import PARAM_MODEL_NAME_IN_DB
from engine.agent.document_react_loader import INITIAL_PROMPT as DEFAULT_DOCUMENT_REACT_LOADER_PROMPT


def seed_smart_rag_components(session: Session):
    document_search = db.Component(
        id=COMPONENT_UUIDS["document_search"],
        name="Document Search",
        description="Document Search for searching documents from a db using documents names",
        release_stage=db.ReleaseStage.BETA,
    )
    upsert_components(
        session=session,
        components=[
            document_search,
        ],
    )
    document_enhanced_llm_call_agent = db.Component(
        id=COMPONENT_UUIDS["document_enhanced_llm_call_agent"],
        name="Document Enhanced LLM Agent",
        description="LLM Call Agent able to load a file and use it as context",
        is_agent=False,
        function_callable=False,
        release_stage=db.ReleaseStage.BETA,
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["default_document_enhanced_llm_agent"],
    )
    document_react_loader_agent = db.Component(
        id=COMPONENT_UUIDS["document_react_loader_agent"],
        name="Document AI Agent",
        description="React Agent able to call a document llm loader agent as a tool",
        is_agent=False,
        function_callable=False,
        release_stage=db.ReleaseStage.BETA,
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["default_tool_description"],
    )
    upsert_components(
        session=session,
        components=[
            document_enhanced_llm_call_agent,
            document_react_loader_agent,
        ],
    )
    # document react loader agent
    document_react_loader_agent_document_enhanced_llm_agent_param = db.ComponentParameterDefinition(
        id=UUID("8ff93e7c-9bc3-4855-b9a4-9aabd9f06356"),
        component_id=document_react_loader_agent.id,
        name="document_enhanced_llm_call_agent",
        type=ParameterType.COMPONENT,
        nullable=False,
    )
    # document enhanced llm call agent
    document_enhanced_llm_call_agent_document_search_param = db.ComponentParameterDefinition(
        id=UUID("7facf1a7-47c5-468c-95c9-650a2b883f1f"),
        component_id=document_enhanced_llm_call_agent.id,
        name="document_search",
        type=ParameterType.COMPONENT,
        nullable=False,
    )
    document_enhanced_llm_call_agent_synthesizer_param = db.ComponentParameterDefinition(
        id=UUID("90450c2a-d24d-41e0-85b9-1b0da2661b15"),
        component_id=document_enhanced_llm_call_agent.id,
        name="synthesizer",
        type=ParameterType.COMPONENT,
        nullable=False,
    )
    document_search_db_service_param = db.ComponentParameterDefinition(
        id=UUID("2a36a68a-612c-4533-95b6-c90d17924b78"),
        component_id=document_search.id,
        name="db_service",
        type=ParameterType.COMPONENT,
        nullable=False,
    )

    upsert_components_parameter_definitions(
        session=session,
        component_parameter_definitions=[
            document_react_loader_agent_document_enhanced_llm_agent_param,
            document_enhanced_llm_call_agent_document_search_param,
            document_enhanced_llm_call_agent_synthesizer_param,
            document_search_db_service_param,
        ],
    )

    upsert_components_parameter_child_relationships(
        session=session,
        component_parameter_child_relationships=[
            db.ComponentParameterChildRelationship(
                id=UUID("e8dcf9d9-3ea5-4c8f-bdde-e9d0dddd45de"),
                component_parameter_definition_id=document_react_loader_agent_document_enhanced_llm_agent_param.id,
                child_component_id=document_enhanced_llm_call_agent.id,
            ),
            db.ComponentParameterChildRelationship(
                id=UUID("14cd549b-ccdb-4c29-a315-e97023dec3ac"),
                component_parameter_definition_id=document_enhanced_llm_call_agent_document_search_param.id,
                child_component_id=document_search.id,
            ),
            db.ComponentParameterChildRelationship(
                id=UUID("a0d97386-2eca-477f-81d6-759d0a8833f6"),
                component_parameter_definition_id=document_enhanced_llm_call_agent_synthesizer_param.id,
                child_component_id=COMPONENT_UUIDS["synthesizer"],
            ),
            db.ComponentParameterChildRelationship(
                id=UUID("c2176066-08ed-4b6a-8165-6e05105275c5"),
                component_parameter_definition_id=document_search_db_service_param.id,
                child_component_id=COMPONENT_UUIDS["snowflake_db_service"],
            ),
        ],
    )
    upsert_components_parameter_definitions(
        session=session,
        component_parameter_definitions=[  # Document React loader
            db.ComponentParameterDefinition(
                id=UUID("f70d5b64-72b3-4fc5-a443-6242c58a6a77"),
                component_id=document_react_loader_agent.id,
                name="prompt",
                type=ParameterType.STRING,
                nullable=False,
                default=DEFAULT_DOCUMENT_REACT_LOADER_PROMPT,
                ui_component=UIComponent.TEXTAREA,
                ui_component_properties=UIComponentProperties(
                    label="Initial Prompt for the agent",
                    placeholder="Enter the initial prompt for the agent ({document_tree} is mandatory) on the prompt",
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=False,
            ),
            *build_llm_config_definitions(
                component_id=document_react_loader_agent.id,
                params_to_seed=[
                    ParameterLLMConfig(
                        param_name=PARAM_MODEL_NAME_IN_DB,
                        param_id=UUID("69ae956a-31f0-4349-8d87-115fd42c3356"),
                    ),
                    ParameterLLMConfig(
                        param_name="api_key",
                        param_id=UUID("dcbfd604-bf9c-4339-beaa-31830779fecc"),
                    ),
                ],
            ),
            #  Document Search
            db.ComponentParameterDefinition(
                id=UUID("1589c2b6-a2a9-4d91-9766-ac1b67c6cf81"),
                component_id=document_search.id,
                name="table_name",
                type=ParameterType.STRING,
                nullable=False,
                default="test_smart_rag",
                ui_component=UIComponent.TEXTFIELD,
                ui_component_properties=UIComponentProperties(
                    label="Documents Table Name",
                    placeholder="Table name of the documents to load",
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=False,
            ),
            # TODO: connect directly to source db of ingested data
            db.ComponentParameterDefinition(
                id=UUID("069ef7db-5f01-4d82-a24c-547c1a1b71ca"),
                component_id=document_search.id,
                name="schema_name",
                type=ParameterType.STRING,
                nullable=False,
                default="SMART_RAG",
                ui_component=UIComponent.TEXTFIELD,
                ui_component_properties=UIComponentProperties(
                    label="Document DB Schema Name",
                    placeholder="Schema name of the table of documents to load",
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=False,
            ),
            db.ComponentParameterDefinition(
                id=UUID("22c1be78-4621-4e26-b95a-a9190ce236f1"),
                component_id=document_search.id,
                name="document_name_column",
                type=ParameterType.STRING,
                nullable=False,
                default="document_name",
                ui_component=UIComponent.TEXTFIELD,
                ui_component_properties=UIComponentProperties(
                    label="Document Name column",
                    placeholder="Column name to get the name of the documents to load",
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=False,
            ),
            db.ComponentParameterDefinition(
                id=UUID("92d0d486-bc7d-4c5c-8b70-a01c476c1387"),
                component_id=document_search.id,
                name="content_document_column",
                type=ParameterType.STRING,
                nullable=False,
                default="document_content",
                ui_component=UIComponent.TEXTFIELD,
                ui_component_properties=UIComponentProperties(
                    label="Document Content Column",
                    placeholder="Column name to get the content of the documents",
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=False,
            ),
            db.ComponentParameterDefinition(
                id=UUID("930f33a1-52d3-46d6-95f9-37cd8da7c809"),
                component_id=document_search.id,
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
        ],
    )
