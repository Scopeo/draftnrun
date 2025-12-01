from typing import Any
from uuid import UUID

from engine.agent.inputs_outputs.start import Start
from engine.agent.filter import Filter
from engine.agent.llm_call_agent import LLMCallAgent
from engine.agent.sql.react_sql_tool import ReactSQLAgent
from engine.agent.sql.run_sql_query_tool import RunSQLQueryTool
from engine.agent.sql.sql_tool import SQLTool
from engine.agent.react_function_calling import ReActAgent
from engine.agent.synthesizer import Synthesizer
from engine.agent.hybrid_synthesizer import HybridSynthesizer
from engine.agent.rag.rag import RAG
from engine.agent.rag.hybrid_rag import HybridRAG
from engine.agent.rag.chunk_selection import RelevantChunkSelector
from engine.agent.rag.formatter import Formatter
from engine.agent.rag.retriever import Retriever
from engine.agent.rag.cohere_reranker import CohereReranker
from engine.agent.rag.vocabulary_search import VocabularySearch
from engine.agent.tools.tavily_search_tool import TavilyApiTool
from engine.agent.web_search_tool_openai import WebSearchOpenAITool
from engine.agent.tools.api_call_tool import APICallTool
from engine.agent.tools.python_code_runner import PythonCodeRunner
from engine.agent.tools.terminal_command_runner import TerminalCommandRunner
from engine.agent.pdf_generation_tool import PDFGenerationTool
from engine.agent.docx_generation_tool import DOCXGenerationTool
from engine.agent.tools.docx_template import DocxTemplateAgent
from engine.agent.document_enhanced_llm_call import DocumentEnhancedLLMCallAgent
from engine.agent.document_react_loader import DocumentReactLoaderAgent
from engine.agent.ocr_call import OCRCall
from engine.agent.rag.document_search import DocumentSearch
from engine.agent.graph_runner_block import GraphRunnerBlock
from engine.agent.chunk_processor import ChunkProcessor
from engine.integrations.gmail_sender import GmailSender
from engine.agent.tools.linkup_tool import LinkupSearchTool
from engine.storage_service.local_service import SQLLocalService
from engine.storage_service.snowflake_service.snowflake_service import SnowflakeService
from ada_backend.services.entity_factory import (
    EntityFactory,
    AgentFactory,
    NonToolCallableBlockFactory,
    detect_and_convert_dataclasses,
    build_trace_manager_processor,
    build_completion_service_processor,
    build_param_name_translator,
    build_qdrant_service_processor,
    compose_processors,
    build_web_service_processor,
    build_ocr_service_processor,
    build_project_reference_processor,
    build_db_service_processor,
    build_retriever_processor,
    build_synthesizer_processor,
    build_reranker_processor,
    build_vocabulary_search_processor,
    build_formatter_processor,
    build_llm_capability_resolver_processor,
)
from ada_backend.database.seed.constants import (
    COMPLETION_MODEL_IN_DB,
    EMBEDDING_MODEL_IN_DB,
    TEMPERATURE_IN_DB,
    VERBOSITY_IN_DB,
    REASONING_IN_DB,
)
from ada_backend.database.seed.utils import COMPONENT_VERSION_UUIDS
from engine.agent.static_responder import StaticResponder


class FactoryRegistry:
    """
    A registry for factories, allowing flexible registration and instantiation
    of entities (agents, components, etc.) by component version ID.
    """

    def __init__(self) -> None:
        self._registry: dict[UUID, EntityFactory] = {}

    def register(
        self,
        component_version_id: UUID,
        factory: EntityFactory,
    ) -> None:
        """
        Register a factory with the registry.

        Args:
            component_version_id (UUID): The component version ID to register the factory under.
            factory (EntityFactory): The factory class responsible for creating the entity.
        """
        self._registry[component_version_id] = factory

    def get(self, component_version_id: UUID) -> EntityFactory:
        """
        Retrieve the factory for a registered entity.

        Args:
            component_version_id (UUID): The component version ID of the registered entity.

        Returns:
            EntityFactory: The factory for the entity.

        Raises:
            ValueError: If the component version is not registered.
        """
        if component_version_id not in self._registry:
            raise ValueError(f"Component version ID {component_version_id} is not registered.")
        return self._registry[component_version_id]

    def create(
        self,
        component_version_id: UUID,
        *args,
        **kwargs,
    ) -> Any:
        """
        Create an instance of a registered entity using its factory.

        Args:
            component_version_id (UUID): The component version ID of the registered entity.
            *args: Positional arguments for the entity factory.
            **kwargs: Keyword arguments for the entity factory.

        Returns:
            Any: The instantiated entity.
        """
        factory = self.get(component_version_id=component_version_id)
        return factory(*args, **kwargs)

    def list_registered_versions(self) -> list[UUID]:
        """
        List all registered component version IDs.

        Returns:
            list[UUID]: The list of registered component version IDs.
        """
        return list(self._registry.keys())


def create_factory_registry() -> FactoryRegistry:
    """
    Create a new entity registry with the default entities registered.

    Returns:
        FactoryRegistry: The entity registry with default entities.
    """
    registry = FactoryRegistry()

    trace_manager_processor = build_trace_manager_processor()

    completion_service_processor = compose_processors(
        build_param_name_translator(
            {
                # Name from DB -> Name in processor
                COMPLETION_MODEL_IN_DB: "completion_model",
                TEMPERATURE_IN_DB: "temperature",
                VERBOSITY_IN_DB: "verbosity",
                REASONING_IN_DB: "reasoning",
                "api_key": "llm_api_key",
            }
        ),
        build_completion_service_processor(),
    )
    qdrant_service_processor = compose_processors(
        build_param_name_translator(
            {
                "qdrant_collection_schema": "default_collection_schema",
                EMBEDDING_MODEL_IN_DB: "embedding_model",
                "api_key": "llm_api_key",
            }
        ),
        build_qdrant_service_processor(),
    )
    web_service_processor = compose_processors(
        build_param_name_translator(
            {
                COMPLETION_MODEL_IN_DB: "completion_model",
                "api_key": "llm_api_key",
            }
        ),
        build_web_service_processor(),
    )
    ocr_service_processor = compose_processors(
        build_param_name_translator(
            {
                COMPLETION_MODEL_IN_DB: "completion_model",
                "api_key": "llm_api_key",
            }
        ),
        build_ocr_service_processor(),
    )
    synthesizer_processor = compose_processors(
        build_param_name_translator(
            {
                "api_key": "llm_api_key",
            }
        ),
        build_synthesizer_processor(),
    )
    retriever_processor = compose_processors(
        build_param_name_translator(
            {
                "api_key": "llm_api_key",
            }
        ),
        build_retriever_processor(),
    )
    reranker_processor = build_reranker_processor()
    vocabulary_search_processor = build_vocabulary_search_processor()
    formatter_processor = build_formatter_processor()
    db_service_processor = build_db_service_processor()
    llm_capability_resolver_processor = build_llm_capability_resolver_processor()

    # Register components
    registry.register(
        component_version_id=COMPONENT_VERSION_UUIDS["synthesizer"],
        factory=EntityFactory(
            entity_class=Synthesizer,
            parameter_processors=[
                completion_service_processor,
                detect_and_convert_dataclasses,
                trace_manager_processor,
            ],
        ),
    )
    registry.register(
        component_version_id=COMPONENT_VERSION_UUIDS["hybrid_synthesizer"],
        factory=EntityFactory(
            entity_class=HybridSynthesizer,
            parameter_processors=[
                completion_service_processor,
                detect_and_convert_dataclasses,
                trace_manager_processor,
            ],
        ),
    )
    registry.register(
        component_version_id=COMPONENT_VERSION_UUIDS["relevant_chunk_selector"],
        factory=EntityFactory(
            entity_class=RelevantChunkSelector,
            parameter_processors=[
                completion_service_processor,
                detect_and_convert_dataclasses,
            ],
        ),
    )
    registry.register(
        component_version_id=COMPONENT_VERSION_UUIDS["retriever"],
        factory=EntityFactory(
            entity_class=Retriever,
            parameter_processors=[
                trace_manager_processor,
                qdrant_service_processor,
            ],
        ),
    )
    registry.register(
        component_version_id=COMPONENT_VERSION_UUIDS["cohere_reranker"],
        factory=EntityFactory(
            entity_class=CohereReranker,
            parameter_processors=[trace_manager_processor],
        ),
    )

    registry.register(
        component_version_id=COMPONENT_VERSION_UUIDS["formatter"],
        factory=EntityFactory(
            entity_class=Formatter,
        ),
    )
    registry.register(
        component_version_id=COMPONENT_VERSION_UUIDS["vocabulary_search"],
        factory=EntityFactory(
            entity_class=VocabularySearch,
            parameter_processors=[trace_manager_processor],
        ),
    )
    registry.register(
        component_version_id=COMPONENT_VERSION_UUIDS["sql_db_service"],
        factory=EntityFactory(
            entity_class=SQLLocalService,
        ),
    )
    registry.register(
        component_version_id=COMPONENT_VERSION_UUIDS["snowflake_db_service"],
        factory=EntityFactory(
            entity_class=SnowflakeService,
        ),
    )
    registry.register(
        component_version_id=COMPONENT_VERSION_UUIDS["document_search"],
        factory=EntityFactory(
            entity_class=DocumentSearch,
            parameter_processors=[trace_manager_processor],
        ),
    )

    # Register agents
    registry.register(
        component_version_id=COMPONENT_VERSION_UUIDS["base_ai_agent"],
        factory=AgentFactory(
            entity_class=ReActAgent,
            parameter_processors=[
                completion_service_processor,
            ],
        ),
    )
    registry.register(
        component_version_id=COMPONENT_VERSION_UUIDS["llm_call"],
        factory=AgentFactory(
            entity_class=LLMCallAgent,
            parameter_processors=[
                completion_service_processor,
                llm_capability_resolver_processor,
            ],
        ),
    )
    registry.register(
        component_version_id=COMPONENT_VERSION_UUIDS["project_reference"],
        factory=NonToolCallableBlockFactory(
            entity_class=GraphRunnerBlock,
            parameter_processors=[
                build_project_reference_processor(),
            ],
        ),
    )
    registry.register(
        component_version_id=COMPONENT_VERSION_UUIDS["chunk_processor"],
        factory=NonToolCallableBlockFactory(
            entity_class=ChunkProcessor,
            parameter_processors=[
                build_project_reference_processor(),
            ],
        ),
    )
    registry.register(
        component_version_id=COMPONENT_VERSION_UUIDS["ocr_call"],
        factory=AgentFactory(
            entity_class=OCRCall,
            parameter_processors=[
                ocr_service_processor,
            ],
        ),
    )
    registry.register(
        component_version_id=COMPONENT_VERSION_UUIDS["rag_agent"],
        factory=AgentFactory(
            entity_class=RAG,
        ),
    )
    registry.register(
        component_version_id=COMPONENT_VERSION_UUIDS["rag_agent_v2"],
        factory=AgentFactory(
            entity_class=RAG,
            parameter_processors=[
                retriever_processor,
                synthesizer_processor,
            ],
        ),
    )
    registry.register(
        component_version_id=COMPONENT_VERSION_UUIDS["rag_agent_v3"],
        factory=AgentFactory(
            entity_class=RAG,
            parameter_processors=[
                retriever_processor,
                synthesizer_processor,
                reranker_processor,
                vocabulary_search_processor,
                formatter_processor,
            ],
        ),
    )
    registry.register(
        component_version_id=COMPONENT_VERSION_UUIDS["hybrid_rag_agent"],
        factory=AgentFactory(
            entity_class=HybridRAG,
        ),
    )
    registry.register(
        component_version_id=COMPONENT_VERSION_UUIDS["tavily_agent"],
        factory=AgentFactory(
            entity_class=TavilyApiTool,
            parameter_processors=[
                completion_service_processor,
            ],
        ),
    )
    web_search_factory = AgentFactory(
        entity_class=WebSearchOpenAITool,
        parameter_processors=[
            web_service_processor,
        ],
    )
    registry.register(
        component_version_id=COMPONENT_VERSION_UUIDS["web_search_openai_agent"], factory=web_search_factory
    )
    registry.register(
        component_version_id=COMPONENT_VERSION_UUIDS["web_search_openai_agent_v2"], factory=web_search_factory
    )
    registry.register(
        component_version_id=COMPONENT_VERSION_UUIDS["api_call_tool"],
        factory=AgentFactory(
            entity_class=APICallTool,
        ),
    )
    registry.register(
        component_version_id=COMPONENT_VERSION_UUIDS["python_code_runner"],
        factory=AgentFactory(
            entity_class=PythonCodeRunner,
        ),
    )
    registry.register(
        component_version_id=COMPONENT_VERSION_UUIDS["terminal_command_runner"],
        factory=AgentFactory(
            entity_class=TerminalCommandRunner,
        ),
    )
    registry.register(
        component_version_id=COMPONENT_VERSION_UUIDS["pdf_generation"],
        factory=AgentFactory(
            entity_class=PDFGenerationTool,
            parameter_processors=[
                trace_manager_processor,
            ],
        ),
    )
    registry.register(
        component_version_id=COMPONENT_VERSION_UUIDS["docx_generation"],
        factory=AgentFactory(
            entity_class=DOCXGenerationTool,
            parameter_processors=[
                trace_manager_processor,
            ],
        ),
    )
    registry.register(
        component_version_id=COMPONENT_VERSION_UUIDS["sql_tool"],
        factory=AgentFactory(
            entity_class=SQLTool,
            parameter_processors=[
                completion_service_processor,
            ],
        ),
    )
    registry.register(
        component_version_id=COMPONENT_VERSION_UUIDS["linkup_search_tool"],
        factory=AgentFactory(
            entity_class=LinkupSearchTool,
        ),
    )
    registry.register(
        component_version_id=COMPONENT_VERSION_UUIDS["react_sql_agent"],
        factory=AgentFactory(
            entity_class=ReactSQLAgent,
            parameter_processors=[
                completion_service_processor,
            ],
        ),
    )
    registry.register(
        component_version_id=COMPONENT_VERSION_UUIDS["react_sql_agent_v2"],
        factory=AgentFactory(
            entity_class=ReactSQLAgent,
            parameter_processors=[
                db_service_processor,
                completion_service_processor,
            ],
        ),
    )
    registry.register(
        component_version_id=COMPONENT_VERSION_UUIDS["run_sql_query_tool"],
        factory=AgentFactory(
            entity_class=RunSQLQueryTool,
        ),
    )
    registry.register(
        component_version_id=COMPONENT_VERSION_UUIDS["document_enhanced_llm_call_agent"],
        factory=AgentFactory(
            entity_class=DocumentEnhancedLLMCallAgent,
        ),
    )
    registry.register(
        component_version_id=COMPONENT_VERSION_UUIDS["document_react_loader_agent"],
        factory=AgentFactory(
            entity_class=DocumentReactLoaderAgent,
            parameter_processors=[
                completion_service_processor,
            ],
        ),
    )
    registry.register(
        component_version_id=COMPONENT_VERSION_UUIDS["static_responder"],
        factory=AgentFactory(
            entity_class=StaticResponder,
        ),
    )

    registry.register(
        component_version_id=COMPONENT_VERSION_UUIDS["start"],
        factory=AgentFactory(
            entity_class=Start,
        ),
    )
    registry.register(
        component_version_id=COMPONENT_VERSION_UUIDS["start_v2"],
        factory=AgentFactory(
            entity_class=Start,
        ),
    )

    registry.register(
        component_version_id=COMPONENT_VERSION_UUIDS["filter"],
        factory=AgentFactory(
            entity_class=Filter,
        ),
    )

    registry.register(
        component_version_id=COMPONENT_VERSION_UUIDS["gmail_sender"],
        factory=AgentFactory(
            entity_class=GmailSender,
        ),
    )

    registry.register(
        component_version_id=COMPONENT_VERSION_UUIDS["docx_template_agent"],
        factory=AgentFactory(
            entity_class=DocxTemplateAgent,
            parameter_processors=[
                completion_service_processor,
            ],
        ),
    )

    return registry


FACTORY_REGISTRY = create_factory_registry()
