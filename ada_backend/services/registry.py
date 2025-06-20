from typing import Any
from enum import StrEnum

from engine.agent.inputs_outputs.input import Input
from engine.agent.llm_call_agent import LLMCallAgent
from engine.agent.sql.react_sql_tool import ReactSQLAgent
from engine.agent.sql.run_sql_query_tool import RunSQLQueryTool
from engine.agent.sql.sql_tool import SQLTool
from engine.agent.static_responder import StaticResponder
from engine.agent.react_function_calling import ReActAgent
from engine.agent.synthesizer import Synthesizer
from engine.agent.hybrid_synthesizer import HybridSynthesizer
from engine.agent.sequential_pipeline import SequentialPipeline
from engine.agent.switch_categorical_pipeline import SwitchCategoricalPipeline
from engine.agent.rag.rag import RAG
from engine.agent.rag.hybrid_rag import HybridRAG
from engine.agent.rag.chunk_selection import RelevantChunkSelector
from engine.agent.rag.formatter import Formatter
from engine.agent.rag.retriever import Retriever
from engine.agent.rag.cohere_reranker import CohereReranker
from engine.agent.rag.vocabulary_search import VocabularySearch
from engine.agent.api_tools.tavily_search_tool import TavilyApiTool
from engine.agent.web_search_tool_openai import WebSearchOpenAITool
from engine.agent.api_tools.api_call_tool import APICallTool
from engine.agent.document_enhanced_llm_call import DocumentEnhancedLLMCallAgent
from engine.agent.document_react_loader import DocumentReactLoaderAgent
from engine.agent.rag.document_search import DocumentSearch
from engine.storage_service.local_service import SQLLocalService
from engine.storage_service.snowflake_service.snowflake_service import SnowflakeService
from engine.trace.trace_manager import TraceManager
from ada_backend.services.entity_factory import (
    EntityFactory,
    AgentFactory,
    detect_and_convert_dataclasses,
    build_trace_manager_processor,
    build_llm_service_processor,
    build_param_name_translator,
    build_qdrant_service_processor,
    compose_processors,
)

PARAM_MODEL_NAME_IN_DB = "model_name"


class SupportedEntityType(StrEnum):
    """
    Supported entity types for instantiation. The names should match
    the component names in the database.
    """

    # Components
    SYNTHESIZER = "Synthesizer"
    HYBRRID_SYNTHESIZER = "HybridSynthesizer"
    RETRIEVER = "Retriever"
    COHERE_RERANKER = "CohereReranker"
    RAG_ANSWER_FORMATTER = "Formatter"
    VOCABULARY_SEARCH = "Vocabulary Search"
    SQL_DB_SERVICE = "SQLDBService"
    CHUNK_SELECTOR = "ChunkSelector"
    DOCUMENT_SEARCH = "Document Search"
    # Agents
    REACT_AGENT = "AI Agent"
    RAG_AGENT = "RAG"
    HYBRID_RAG_AGENT = "HybridRAGAgent"
    SNOWFLAKE_DB_SERVICE = "SnowflakeDBService"
    TAVILY_AGENT = "Internet Search with Tavily"
    OPENAI_WEB_SEARCH_AGENT = "Internet Search with OpenAI"
    API_CALL_TOOL = "API Call"
    SEQUENTIAL_PIPELINE = "SequentialPipeline"
    SWITCH_CATEGORICAL_PIPELINE = "SwitchCategoricalPipeline"
    STATIC_RESPONDER = "StaticResponder"
    SQL_TOOL = "SQLTool"
    LLM_CALL_AGENT = "LLM Call"
    REACT_SQL_AGENT = "Database Query Agent"
    RUN_SQL_QUERY_TOOL = "RunSQLQueryTool"
    DOCUMENT_ENHANCED_LLM_CALL = "Document Enhanced LLM Agent"
    DOCUMENT_REACT_LOADER_AGENT = "Document AI Agent"
    INPUT = "Input"


class FactoryRegistry:
    """
    A registry for factories, allowing flexible registration and instantiation
    of entities (agents, components, etc.).
    """

    def __init__(self) -> None:
        self._registry: dict[str, EntityFactory] = {}

    def register(
        self,
        name: str,
        factory: EntityFactory,
    ) -> None:
        """
        Register a factory with the registry.

        Args:
            name (str): The name of the entity to register.
            factory (EntityFactory): The factory class responsible for creating the entity.
        """
        if name not in SupportedEntityType:
            raise ValueError(f"Entity type '{name}' is not supported.")

        self._registry[name] = factory

    def get(self, entity_name: str) -> EntityFactory:
        """
        Retrieve the factory for a registered entity.

        Args:
            name (str): The name of the registered entity.

        Returns:
            EntityFactory[Any]: The factory for the entity.
        """
        if entity_name not in self._registry:
            raise ValueError(f"Entity '{entity_name}' is not registered.")
        return self._registry[entity_name]

    def create(self, entity_name: str, *args, **kwargs) -> Any:
        """
        Create an instance of a registered entity using its factory.

        Args:
            name (str): The name of the registered entity.
            *args: Positional arguments for the entity factory.
            **kwargs: Keyword arguments for the entity factory.

        Returns:
            Any: The instantiated entity.
        """
        factory = self.get(entity_name)
        return factory(*args, **kwargs)

    def list_supported(self) -> list[str]:
        """
        List the supported entity types.

        Returns:
            list[str]: The list of supported entity types.
        """
        return [entity_type.value for entity_type in SupportedEntityType]


def create_factory_registry() -> FactoryRegistry:
    """
    Create a new entity registry with the default entities registered.

    Returns:
        FactoryRegistry: The entity registry with default entities.
    """
    # TODO: Remove from here when Trace Manager is implemented as thread-safe singleton
    trace_manager = TraceManager(project_name="ada_backend")

    registry = FactoryRegistry()
    trace_manager_processor = build_trace_manager_processor(trace_manager)
    llm_service_processor = compose_processors(
        build_param_name_translator(
            {
                # Name from DB -> Name in processor
                PARAM_MODEL_NAME_IN_DB: "llm_model",
                "web_search_model_name": "llm_model",
                "default_temperature": "llm_temperature",
                "embedding_model_name": "embedding_model_name",
                "api_key": "llm_api_key",
            }
        ),
        build_llm_service_processor(trace_manager),
    )
    qdrant_service_processor = compose_processors(
        build_param_name_translator(
            {
                "qdrant_collection_schema": "default_collection_schema",
                "embedding_model_name": "embedding_model_name",
            }
        ),
        build_qdrant_service_processor(trace_manager),
    )
    # Register components
    registry.register(
        name=SupportedEntityType.SYNTHESIZER,
        factory=EntityFactory(
            entity_class=Synthesizer,
            parameter_processors=[
                llm_service_processor,
                detect_and_convert_dataclasses,
                trace_manager_processor,
            ],
        ),
    )
    registry.register(
        name=SupportedEntityType.HYBRRID_SYNTHESIZER,
        factory=EntityFactory(
            entity_class=HybridSynthesizer,
            parameter_processors=[
                llm_service_processor,
                detect_and_convert_dataclasses,
                trace_manager_processor,
            ],
        ),
    )
    registry.register(
        name=SupportedEntityType.CHUNK_SELECTOR,
        factory=EntityFactory(
            entity_class=RelevantChunkSelector,
            parameter_processors=[
                llm_service_processor,
                detect_and_convert_dataclasses,
            ],
        ),
    )
    registry.register(
        name=SupportedEntityType.RETRIEVER,
        factory=EntityFactory(
            entity_class=Retriever,
            parameter_processors=[
                trace_manager_processor,
                qdrant_service_processor,
            ],
        ),
    )
    registry.register(
        name=SupportedEntityType.COHERE_RERANKER,
        factory=EntityFactory(
            entity_class=CohereReranker,
            parameter_processors=[trace_manager_processor],
        ),
    )

    registry.register(
        name=SupportedEntityType.RAG_ANSWER_FORMATTER,
        factory=EntityFactory(
            entity_class=Formatter,
        ),
    )
    registry.register(
        name=SupportedEntityType.VOCABULARY_SEARCH,
        factory=EntityFactory(
            entity_class=VocabularySearch,
            parameter_processors=[trace_manager_processor],
        ),
    )
    registry.register(
        name=SupportedEntityType.SQL_DB_SERVICE,
        factory=EntityFactory(
            entity_class=SQLLocalService,
        ),
    )
    registry.register(
        name=SupportedEntityType.SNOWFLAKE_DB_SERVICE,
        factory=EntityFactory(
            entity_class=SnowflakeService,
        ),
    )
    registry.register(
        name=SupportedEntityType.DOCUMENT_SEARCH,
        factory=EntityFactory(
            entity_class=DocumentSearch,
            parameter_processors=[trace_manager_processor],
        ),
    )

    # Register agents
    registry.register(
        name=SupportedEntityType.REACT_AGENT,
        factory=AgentFactory(
            entity_class=ReActAgent,
            trace_manager=trace_manager,
            parameter_processors=[
                llm_service_processor,
            ],
        ),
    )
    registry.register(
        name=SupportedEntityType.LLM_CALL_AGENT,
        factory=AgentFactory(
            entity_class=LLMCallAgent,
            trace_manager=trace_manager,
            parameter_processors=[
                llm_service_processor,
            ],
        ),
    )
    registry.register(
        name=SupportedEntityType.RAG_AGENT,
        factory=AgentFactory(entity_class=RAG, trace_manager=trace_manager),
    )
    registry.register(
        name=SupportedEntityType.HYBRID_RAG_AGENT,
        factory=AgentFactory(entity_class=HybridRAG, trace_manager=trace_manager),
    )
    registry.register(
        name=SupportedEntityType.TAVILY_AGENT,
        factory=AgentFactory(
            entity_class=TavilyApiTool,
            trace_manager=trace_manager,
            parameter_processors=[
                llm_service_processor,
            ],
        ),
    )
    registry.register(
        name=SupportedEntityType.OPENAI_WEB_SEARCH_AGENT,
        factory=AgentFactory(
            entity_class=WebSearchOpenAITool,
            trace_manager=trace_manager,
            parameter_processors=[
                llm_service_processor,
            ],
        ),
    )
    registry.register(
        name=SupportedEntityType.API_CALL_TOOL,
        factory=AgentFactory(
            entity_class=APICallTool,
            trace_manager=trace_manager,
        ),
    )
    registry.register(
        name=SupportedEntityType.SEQUENTIAL_PIPELINE,
        factory=AgentFactory(
            entity_class=SequentialPipeline,
            trace_manager=trace_manager,
        ),
    )
    registry.register(
        name=SupportedEntityType.SWITCH_CATEGORICAL_PIPELINE,
        factory=AgentFactory(
            entity_class=SwitchCategoricalPipeline,
            trace_manager=trace_manager,
            parameter_processors=[
                llm_service_processor,
            ],
        ),
    )
    registry.register(
        name=SupportedEntityType.STATIC_RESPONDER,
        factory=AgentFactory(
            entity_class=StaticResponder,
            trace_manager=trace_manager,
        ),
    ),
    registry.register(
        name=SupportedEntityType.SQL_TOOL,
        factory=AgentFactory(
            entity_class=SQLTool,
            trace_manager=trace_manager,
            parameter_processors=[
                llm_service_processor,
            ],
        ),
    )
    registry.register(
        name=SupportedEntityType.REACT_SQL_AGENT,
        factory=AgentFactory(
            entity_class=ReactSQLAgent,
            trace_manager=trace_manager,
            parameter_processors=[
                llm_service_processor,
            ],
        ),
    )
    registry.register(
        name=SupportedEntityType.RUN_SQL_QUERY_TOOL,
        factory=AgentFactory(
            entity_class=RunSQLQueryTool,
            trace_manager=trace_manager,
        ),
    )
    registry.register(
        name=SupportedEntityType.DOCUMENT_ENHANCED_LLM_CALL,
        factory=AgentFactory(
            entity_class=DocumentEnhancedLLMCallAgent,
            trace_manager=trace_manager,
        ),
    )
    registry.register(
        name=SupportedEntityType.DOCUMENT_REACT_LOADER_AGENT,
        factory=AgentFactory(
            entity_class=DocumentReactLoaderAgent,
            trace_manager=trace_manager,
            parameter_processors=[
                llm_service_processor,
            ],
        ),
    )

    registry.register(
        name=SupportedEntityType.INPUT,
        factory=AgentFactory(
            entity_class=Input,
            trace_manager=trace_manager,
        ),
    )

    return registry


FACTORY_REGISTRY = create_factory_registry()
