import logging
import json
import asyncio
import concurrent.futures
import contextvars
from inspect import signature
from typing import Optional, Any, Type, Callable, get_type_hints, get_origin, get_args, Union
from uuid import UUID
from dataclasses import is_dataclass
from pydantic import BaseModel

from engine.agent.types import ToolDescription
from engine.agent.rag.retriever import Retriever
from engine.agent.rag.cohere_reranker import CohereReranker
from engine.agent.rag.vocabulary_search import VocabularySearch
from engine.agent.rag.formatter import Formatter
from engine.agent.synthesizer import Synthesizer
from engine.trace.trace_context import get_trace_manager
from engine.llm_services.llm_service import EmbeddingService, CompletionService, WebSearchService, OCRService
from engine.qdrant_service import QdrantService, QdrantCollectionSchema
from ada_backend.database.setup_db import get_db_session
from ada_backend.database.models import EnvType
from ada_backend.repositories.source_repository import get_data_source_by_id
from ada_backend.repositories.project_repository import get_project
from ada_backend.context import get_request_context
from ada_backend.services.user_roles_service import get_user_access_to_organization
from ada_backend.services.llm_models_service import (
    get_llm_models_by_capability_select_options_service,
    get_model_id_by_name_service,
)
from ada_backend.services.errors import MissingDataSourceError
from engine.storage_service.local_service import SQLLocalService

LOGGER = logging.getLogger(__name__)

ParameterProcessor = Callable[[dict, dict[str, Any]], dict]


class ParameterToValidate(BaseModel):
    argument: Any
    type: Any
    optional: bool = False


# TODO: Remove this when llm service has only model_id as an argument
def fetch_model_id_by_name(model_name: str) -> UUID | None:
    with get_db_session() as session:
        return get_model_id_by_name_service(session, model_name)


class EntityFactory:
    """
    Base class for creating instances of entities (agents, components, etc.).
    Provides a flexible interface for instantiation using configuration data.
    """

    def __init__(
        self,
        entity_class: Type[Any],
        parameter_processors: Optional[list[ParameterProcessor]] = None,
        constructor_method: str = "__init__",
    ):
        """
        Initialize the factory with the class or callable used for instantiation.

        Args:
            entity_class (Type[Any]): The class or callable to use for creating entities.
            parameter_processors (Optional[list[ParameterProcessor]], optional):
                A list of functions to preprocess the entity constructor parameters.
            constructor_method (str, optional): The method to use for instantiation.
                Defaults to "__init__".
        """
        self.entity_class = entity_class
        self.constructor_method = constructor_method
        self.parameter_processors = parameter_processors or []
        self.constructor_params = self._get_constructor_params()

    def _get_constructor_params(self) -> dict[str, Any]:
        """
        Retrieve the parameters for the specified constructor method of the entity class.

        Returns:
            dict[str, Any]: A mapping of parameter names to their types.
        """
        if not hasattr(self.entity_class, self.constructor_method):
            raise ValueError(
                f"{self.entity_class.__name__} does not have a method named '{self.constructor_method}'.",
            )

        method = getattr(self.entity_class, self.constructor_method)
        if not callable(method):
            raise ValueError(
                f"'{self.constructor_method}' is not callable on {self.entity_class.__name__}.",
            )

        hints = get_type_hints(method)
        params = signature(method).parameters
        return {
            name: hints.get(name, param.annotation)
            for name, param in params.items()
            if param.annotation is not param.empty
        }

    def _process_parameters(self, *args, **kwargs) -> tuple[tuple, dict]:
        """
        Preprocess the arguments before instantiation.

        Args:
            *args: Positional arguments for the entity constructor.
            **kwargs: Keyword arguments for the entity constructor.

        Returns:
            tuple[tuple, dict]: Processed positional and keyword arguments.
        """
        for processor in self.parameter_processors:
            kwargs = processor(kwargs, self.constructor_params)
        return args, kwargs

    def __call__(self, *args, **kwargs) -> Any:
        """
        Create an instance of the entity using the provided arguments.

        Args:
            *args: Positional arguments for the entity constructor.
            **kwargs: Keyword arguments for the entity constructor.

        Returns:
            Any: The instantiated entity.
        """
        args, kwargs = self._process_parameters(*args, **kwargs)
        if self.constructor_method == "__init__":
            # Call the constructor directly
            return self.entity_class(*args, **kwargs)

        constructor_method = getattr(self.entity_class, self.constructor_method, None)
        if not callable(constructor_method):
            raise ValueError(
                f"Method '{self.constructor_method}' is not callable on {self.entity_class.__name__}.",
            )
        return constructor_method(*args, **kwargs)


class AgentFactory(EntityFactory):
    """
    Factory class for creating Agent instances.
    """

    def __init__(
        self,
        entity_class: Type[Any],
        parameter_processors: Optional[list[ParameterProcessor]] = None,
        constructor_method: str = "__init__",
    ):
        """
        Initialize the AgentFactory.

        Args:
            entity_class (Type[Any]): The class or callable to use for creating agents.
            parameter_processors (Optional[list[ParameterProcessor]]): A list of
                parameter processors.
        """
        processors = parameter_processors or []
        processors.append(build_trace_manager_processor())

        super().__init__(
            entity_class=entity_class,
            parameter_processors=processors,
            constructor_method=constructor_method,
        )
        self.trace_manager = get_trace_manager()

    def _process_parameters(self, *args, **kwargs) -> tuple[tuple, dict]:
        args, kwargs = super()._process_parameters(*args, **kwargs)

        tool_description = kwargs.get("tool_description")
        if not isinstance(tool_description, ToolDescription):
            raise ValueError("Tool description must be a ToolDescription object.")

        return args, kwargs


class NonToolCallableBlockFactory(EntityFactory):
    """
    Factory for agent-like blocks that are not meant to be function-callable.

    Differences from AgentFactory:
    - Does NOT enforce the presence/type of a ToolDescription in params.
    - Still injects a trace manager when the target constructor accepts it.
    """

    def __init__(
        self,
        entity_class: Type[Any],
        parameter_processors: Optional[list[ParameterProcessor]] = None,
        constructor_method: str = "__init__",
    ):
        processors = parameter_processors or []
        processors.append(build_trace_manager_processor())

        super().__init__(
            entity_class=entity_class,
            parameter_processors=processors,
            constructor_method=constructor_method,
        )


def build_dataclass_processor(dataclass_type: Type[Any], param_name: str) -> ParameterProcessor:
    """
    Creates a processor for converting a specific parameter to a specific dataclass type.

    This is an atomic processor that handles one parameter-to-dataclass conversion.

    Args:
        dataclass_type: The dataclass type to convert to
        param_name: The name of the parameter to process

    Returns:
        ParameterProcessor: A processor that converts the specified parameter to the dataclass
    """

    def processor(params: dict, constructor_params: dict[str, Any]) -> dict:
        if param_name in params and not isinstance(params[param_name], dataclass_type):
            try:
                data = params[param_name]
                if isinstance(data, str):
                    try:
                        data = json.loads(data)
                    except json.JSONDecodeError:
                        raise ValueError(f"Invalid JSON for {param_name}: {data}")
                LOGGER.debug(f"Converting {param_name} with data: {data}")
                params[param_name] = dataclass_type(**data)
            except Exception as e:
                LOGGER.error(f"Error converting {param_name} to {dataclass_type.__name__}: {e}")
                raise e
        return params

    return processor


def detect_and_convert_dataclasses(
    params: dict,
    constructor_params: dict[str, Any],
) -> dict:
    """
    Automatically detects and converts parameters to dataclasses based on constructor parameter types.
    """
    for param_name, param_type in constructor_params.items():
        # Handle Optional types by extracting the dataclass type if present
        if get_origin(param_type) is Union:
            param_type = next((arg for arg in get_args(param_type) if is_dataclass(arg)), None)

        # Convert JSON data to a dataclass instance if applicable
        if param_name in params and param_type and is_dataclass(param_type):
            processor = build_dataclass_processor(param_type, param_name)
            params = processor(params, constructor_params)
    return params


def pydantic_processor(params: dict, constructor_params: dict[str, Any]) -> dict:
    """Returns a processor function to handle Pydantic model parameters."""
    for param_name, param_type in constructor_params.items():
        if param_name in params and issubclass(param_type, BaseModel):
            params[param_name] = param_type(**params[param_name])
    return params


def build_trace_manager_processor() -> ParameterProcessor:
    """
    Returns a processor function to inject a trace manager if required.

    Returns:
        ParameterProcessor: A function to process the entity constructor parameters.
    """

    def processor(params: dict, constructor_params: dict[str, Any]) -> dict:
        if "trace_manager" in constructor_params:
            trace_manager = get_trace_manager()
            params.setdefault("trace_manager", trace_manager)
        return params

    return processor


def build_param_name_translator(mapping: dict[str, str]) -> ParameterProcessor:
    """
    Returns a processor function to translate parameter names according to the provided mapping.

    This processor allows factories to accept parameters with different names than
    what their constructors expect, making the interface more flexible.

    Args:
        mapping (dict[str, str]): Dictionary mapping from external parameter names
                                  to internal parameter names.

    Returns:
        ParameterProcessor: A function to process entity constructor parameters.
    """

    def translator(params: dict, constructor_params: dict[str, Any]) -> dict:
        for external_name, internal_name in mapping.items():
            if external_name in params and internal_name not in params:
                params[internal_name] = params.pop(external_name)
        return params

    return translator


def get_llm_provider_and_model(llm_model: str) -> tuple[str, str]:
    """
    Extracts the LLM provider and model name from a string in the format "provider:model_name".

    Args:
        llm_model (str): The LLM model string in "provider:model_name" format.

    Returns:
        tuple[str, str]: A tuple containing the provider and model name.

    Raises:
        ValueError: If the input string is not in the expected format.
    """
    if ":" not in llm_model:
        raise ValueError(f"Invalid LLM model format: {llm_model}. Expected 'provider:model_name'.")
    parts = llm_model.split(":")
    provider = parts[0]
    model = ":".join(parts[1:])
    return provider, model


def build_completion_service_processor(
    target_name: str = "completion_service",
) -> ParameterProcessor:
    """
    Returns a processor function to inject an LLM service into the parameters.

    This processor consumes and removes the following parameters from the input:
    - completion_model: Required. String in "provider:model_name" format (e.g., "openai:gpt-4").
    - temperature: Optional. Float value for sampling temperature.
    - llm_api_key: Optional. API key for the LLM provider.

    The processor creates an appropriate LLMService instance based on the provider
    and injects it into the params dictionary under the key specified by target_name.

    Args:
        target_name (str): The parameter name to use for the created LLM service.
                          Defaults to "embedding_service".

    Returns:
        ParameterProcessor: A function that processes parameters to inject an LLM service.
    """

    def processor(params: dict, constructor_params: dict[str, Any]) -> dict:
        provider, model_name = get_llm_provider_and_model(llm_model=params.pop("completion_model"))

        model_id = fetch_model_id_by_name(model_name)

        completion_service = CompletionService(
            provider=provider,
            model_name=model_name,
            trace_manager=get_trace_manager(),
            temperature=params.pop("temperature", 1.0),
            api_key=params.pop("llm_api_key", None),
            verbosity=params.pop("verbosity", None),
            reasoning=params.pop("reasoning", None),
            model_id=model_id,
        )

        params[target_name] = completion_service
        return params

    return processor


def build_llm_capability_resolver_processor(
    target_name: str = "capability_resolver",
) -> ParameterProcessor:
    """
    Returns a processor that injects a callable for resolving LLM capabilities.

    The injected callable accepts a list of capability strings and returns the set
    of LLM model references supporting all of them, sourced from the database.
    """

    def processor(params: dict, constructor_params: dict[str, Any]) -> dict:
        if target_name not in constructor_params:
            return params

        def resolve_capabilities(capabilities: list[str]) -> set[str]:
            with get_db_session() as session:
                options = get_llm_models_by_capability_select_options_service(session, capabilities)
            return {option.value for option in options}

        params[target_name] = resolve_capabilities
        return params

    return processor


def build_web_service_processor(
    target_name: str = "web_service",
) -> ParameterProcessor:
    """
    Returns a processor function to inject an LLM service into the parameters.
    """

    def processor(params: dict, constructor_params: dict[str, Any]) -> dict:
        provider, model_name = get_llm_provider_and_model(llm_model=params.pop("completion_model"))

        model_id = fetch_model_id_by_name(model_name)

        web_service = WebSearchService(
            trace_manager=get_trace_manager(),
            provider=provider,
            model_name=model_name,
            api_key=params.pop("llm_api_key", None),
            model_id=model_id,
        )

        params[target_name] = web_service
        return params

    return processor


def build_ocr_service_processor(
    target_name: str = "ocr_service",
) -> ParameterProcessor:
    """
    Returns a processor function to inject an OCR service for OCR processing.
    """

    def processor(params: dict, constructor_params: dict[str, Any]) -> dict:
        provider, model_name = get_llm_provider_and_model(llm_model=params.pop("completion_model"))

        model_id = fetch_model_id_by_name(model_name)

        ocr_service = OCRService(
            trace_manager=get_trace_manager(),
            provider=provider,
            model_name=model_name,
            api_key=params.pop("llm_api_key", None),
            model_id=model_id,
        )

        params[target_name] = ocr_service
        return params

    return processor


def build_qdrant_service_processor(target_name: str = "qdrant_service") -> ParameterProcessor:
    """
    Creates a processor that builds a QdrantService from a source ID.

    Args:
        target_name (str): Parameter name for the created QdrantService.

    Returns:
        ParameterProcessor: A processor function that handles QdrantService creation
        and injects the collection name into the params dictionary.
    """

    def processor(params: dict, constructor_params: dict[str, Any]) -> dict:
        source_id_str: str = params.pop("data_source")["id"]
        if not source_id_str:
            raise ValueError("data_source_id is required")
        source_id = UUID(source_id_str)

        # TODO: Temporary solution - needs proper session injection in future refactor.
        with get_db_session() as session:
            source = get_data_source_by_id(session, source_id)
            if source is None:
                raise ValueError(f"Source with id {source_id} not found")

            provider, model_name = get_llm_provider_and_model(llm_model=source.embedding_model_reference)

            embedding_service = EmbeddingService(
                trace_manager=get_trace_manager(),
                api_key=params.pop("llm_api_key", None),
                provider=provider,
                model_name=model_name,
            )
            qdrant_schema = QdrantCollectionSchema(**source.qdrant_schema)
            collection_name = source.qdrant_collection_name

        qdrant_service = QdrantService.from_defaults(
            embedding_service=embedding_service,
            default_collection_schema=qdrant_schema,
        )

        params[target_name] = qdrant_service
        params["collection_name"] = collection_name

        return params

    return processor


def build_project_reference_processor(target_name: str = "graph_runner") -> ParameterProcessor:
    """
    Returns a processor function to build a GraphRunner from a project reference.
    Access control is enforced to ensure the user has permission to use the project.

    Note: This processor calls async functions from sync code using ThreadPoolExecutor
    to avoid event loop conflicts when running inside FastAPI's async context.

    Returns:
        ParameterProcessor: A function that validates project access before instantiation

    Raises:
        ValueError: If user doesn't have access to the referenced project
    """

    def processor(params: dict, constructor_params: dict[str, Any]) -> dict:
        project_id_str: str | None = params.pop("project_id", None)
        if project_id_str is None:
            raise ValueError("project_id is required")
        project_id = UUID(project_id_str)

        context = get_request_context()
        user = context.require_user()

        # Capture the current context including TraceManager.
        current_context = contextvars.copy_context()

        with get_db_session() as session:
            # TODO: Fix circular import issue - these imports are here to avoid
            # circular dependency between entity_factory and agent_runner_service.
            from ada_backend.repositories.graph_runner_repository import get_graph_runner_for_env
            from ada_backend.services.agent_runner_service import get_agent_for_project

            project = get_project(session, project_id)
            if not project:
                raise ValueError(f"Project {project_id} not found")

            # Validate user has access to the project's organization
            try:
                # Run async function in a new thread with copied context to preserve TraceManager
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        current_context.run,
                        asyncio.run,
                        get_user_access_to_organization(
                            user=user,
                            organization_id=project.organization_id,
                        ),
                    )
                    access = future.result()
                LOGGER.info(f"User {user.id} has access to project {project_id} with role {access.role}")
            except ValueError as e:
                raise ValueError(f"Access denied to project {project_id}: {e}") from e

            # Get and instantiate GraphRunner
            graph_runner_in_db = get_graph_runner_for_env(
                session=session,
                project_id=project_id,
                # TODO: Add support for using different GR versions
                env=EnvType.PRODUCTION,
            )
            if graph_runner_in_db is None:
                raise ValueError(
                    f"No production GraphRunner found for project {project_id}. "
                    f"Publish the project to production and try again.",
                )
            gr_id: UUID = graph_runner_in_db.id

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    current_context.run,
                    asyncio.run,
                    get_agent_for_project(
                        session=session,
                        graph_runner_id=gr_id,
                        project_id=project_id,
                    ),
                )
                graph_runner = future.result()

        params[target_name] = graph_runner

        return params

    return processor


def build_db_service_processor(target_name: str = "db_service") -> ParameterProcessor:
    """
    Returns a processor function to instantiate a database service from engine_url.
    """

    def processor(params: dict, constructor_params: dict[str, Any]) -> dict:
        engine_url = params.pop("engine_url", None)
        if not engine_url:
            return params

        try:
            db_service_instance = SQLLocalService(engine_url=engine_url)
            LOGGER.debug("Instantiated SQLLocalService successfully")
        except ConnectionError as e:
            raise ConnectionError(
                f"Failed to connect to database for component '{target_name}' Error: {str(e)}"
            ) from e
        except Exception as e:
            LOGGER.error(f"Error instantiating SQLLocalService: {e}")
            raise ValueError(f"Failed to create DB service: {e}") from e

        params[target_name] = db_service_instance
        return params

    return processor


def build_retriever_processor(target_name: str = "retriever") -> ParameterProcessor:
    """
    Creates a processor that builds a Retriever from data_source (collection_name + embedding model)
    and retriever-specific parameters.

    Args:
        target_name (str): Parameter name for the created Retriever.

    Returns:
        ParameterProcessor: A processor function that handles Retriever creation
    """

    def processor(params: dict, constructor_params: dict[str, Any]) -> dict:
        data_source = params.pop("data_source", None)
        if data_source is None:
            component_attrs = params.get("component_attributes")
            component_name = getattr(component_attrs, "component_instance_name", None)
            raise MissingDataSourceError(component_name)

        if isinstance(data_source, str):
            import json

            data_source = json.loads(data_source)

        source_id_str = data_source.get("id") if isinstance(data_source, dict) else None
        if not source_id_str:
            raise ValueError("data_source must contain an 'id' field")
        source_id = UUID(source_id_str)

        with get_db_session() as session:
            source = get_data_source_by_id(session, source_id)
            if source is None:
                raise ValueError(f"Source with id {source_id} not found")

            provider, model_name = get_llm_provider_and_model(llm_model=source.embedding_model_reference)
            collection_name = source.qdrant_collection_name
            qdrant_schema = QdrantCollectionSchema(**source.qdrant_schema)

        embedding_service = EmbeddingService(
            trace_manager=get_trace_manager(),
            api_key=params.pop("llm_api_key", None),
            provider=provider,
            model_name=model_name,
        )
        qdrant_service = QdrantService.from_defaults(
            embedding_service=embedding_service,
            default_collection_schema=qdrant_schema,
        )
        list_of_params_to_pop = [
            ParameterToValidate(argument="max_retrieved_chunks", type=int, optional=False),
            ParameterToValidate(argument="enable_date_penalty_for_chunks", type=bool, optional=False),
            ParameterToValidate(argument="chunk_age_penalty_rate", type=float, optional=True),
            ParameterToValidate(argument="default_penalty_rate", type=float, optional=True),
            ParameterToValidate(argument="max_retrieved_chunks_after_penalty", type=int, optional=True),
            ParameterToValidate(argument="metadata_date_key", type=str, optional=True),
        ]
        validated_params = _pop_and_validate_parameters(list_of_params_to_pop, params)

        retriever = Retriever(
            trace_manager=get_trace_manager(),
            qdrant_service=qdrant_service,
            collection_name=collection_name,
            component_attributes=None,
            **validated_params,
        )

        params[target_name] = retriever
        return params

    return processor


def build_synthesizer_processor(target_name: str = "synthesizer") -> ParameterProcessor:
    """
    Creates a processor that builds a Synthesizer from completion_model, temperature, prompt_template.

    Args:
        target_name (str): Parameter name for the created Synthesizer.

    Returns:
        ParameterProcessor: A processor function that handles Synthesizer creation
    """

    def processor(params: dict, constructor_params: dict[str, Any]) -> dict:
        completion_model = params.pop("completion_model")
        provider, model_name = get_llm_provider_and_model(llm_model=completion_model)

        temperature = params.pop("temperature", 1.0)
        if temperature is not None:
            try:
                temperature = float(temperature)
            except ValueError as e:
                raise ValueError(f"temperature must be a float, got {temperature}: {e}")

        model_id = fetch_model_id_by_name(model_name)

        completion_service = CompletionService(
            provider=provider,
            model_name=model_name,
            trace_manager=get_trace_manager(),
            temperature=temperature,
            api_key=params.pop("llm_api_key", None),
            verbosity=params.pop("verbosity", None),
            reasoning=params.pop("reasoning", None),
            model_id=model_id,
        )

        prompt_template = params.pop("prompt_template", None)
        if prompt_template is None:
            try:
                prompt_template = str(prompt_template)
            except ValueError as e:
                raise ValueError(f"prompt_template must be a string, got {prompt_template}: {e}")
            if len(prompt_template) == 0:
                raise ValueError("prompt_template must be a non-empty string")

        synthesizer = Synthesizer(
            completion_service=completion_service,
            trace_manager=get_trace_manager(),
            prompt_template=prompt_template,
            component_attributes=None,
        )

        params[target_name] = synthesizer
        return params

    return processor


def build_reranker_processor(target_name: str = "reranker") -> ParameterProcessor:
    """
    Creates a processor that builds a CohereReranker from reranker-specific parameters.
    Only creates the reranker if use_reranker is True.

    Args:
        target_name (str): Parameter name for the created Reranker.

    Returns:
        ParameterProcessor: A processor function that handles Reranker creation
    """

    def processor(params: dict, constructor_params: dict[str, Any]) -> dict:
        use_reranker = _pop_and_validate_parameter(params, "use_reranker", bool, "use_reranker must be a boolean")

        if not use_reranker:
            return _remove_parameters_from_optional_subcomponents(
                params,
                parameters_name=[
                    "cohere_model",
                    "score_threshold",
                    "num_doc_reranked",
                ],
                target_name=target_name,
            )

        list_of_params_to_pop = [
            ParameterToValidate(argument="cohere_model", type=str, optional=False),
            ParameterToValidate(argument="score_threshold", type=float, optional=False),
            ParameterToValidate(argument="num_doc_reranked", type=int, optional=False),
        ]
        validated_params = _pop_and_validate_parameters(list_of_params_to_pop, params)

        reranker_params = {**validated_params}

        reranker = CohereReranker(
            trace_manager=get_trace_manager(),
            component_attributes=None,
            **reranker_params,
        )

        params[target_name] = reranker
        return params

    return processor


def build_vocabulary_search_processor(target_name: str = "vocabulary_search") -> ParameterProcessor:
    """
    Creates a processor that builds a VocabularySearch from vocabulary search parameters.
    Only creates the vocabulary search if use_vocabulary_search is True.

    Args:
        target_name (str): Parameter name for the created VocabularySearch.

    Returns:
        ParameterProcessor: A processor function that handles VocabularySearch creation
    """

    def processor(params: dict, constructor_params: dict[str, Any]) -> dict:
        use_vocabulary_search = _pop_and_validate_parameter(
            params, "use_vocabulary_search", bool, "use_vocabulary_search must be a boolean"
        )

        if not use_vocabulary_search:
            return _remove_parameters_from_optional_subcomponents(
                params,
                parameters_name=[
                    "vocabulary_context_data",
                    "fuzzy_threshold",
                    "fuzzy_matching_candidates",
                    "vocabulary_context_prompt_key",
                ],
                target_name=target_name,
            )
        list_of_params_to_pop = [
            ParameterToValidate(argument="fuzzy_threshold", type=int, optional=False),
            ParameterToValidate(argument="fuzzy_matching_candidates", type=int, optional=False),
            ParameterToValidate(argument="vocabulary_context_prompt_key", type=str, optional=False),
        ]
        validated_params = _pop_and_validate_parameters(list_of_params_to_pop, params)

        vocabulary_context_data = params.pop("vocabulary_context_data")
        if isinstance(vocabulary_context_data, str):
            try:
                vocabulary_context_data = json.loads(vocabulary_context_data)
            except json.JSONDecodeError as e:
                raise ValueError(f"vocabulary_context_data must be valid JSON, got {vocabulary_context_data}: {e}")

        if not isinstance(vocabulary_context_data, dict):
            raise ValueError(f"vocabulary_context_data must be a dict, got {type(vocabulary_context_data)}")

        vocab_params = {"vocabulary_context_data": vocabulary_context_data, **validated_params}

        vocabulary_search = VocabularySearch(
            trace_manager=get_trace_manager(),
            component_attributes=None,
            **vocab_params,
        )

        params[target_name] = vocabulary_search
        return params

    return processor


def build_formatter_processor(target_name: str = "formatter") -> ParameterProcessor:
    """
    Creates a processor that builds a Formatter from formatter parameters.
    Only creates the formatter if use_formatter is True.

    Args:
        target_name (str): Parameter name for the created Formatter.

    Returns:
        ParameterProcessor: A processor function that handles Formatter creation
    """

    def processor(params: dict, constructor_params: dict[str, Any]) -> dict:
        use_formatter = _pop_and_validate_parameter(params, "use_formatter", bool, "use_formatter must be a boolean")

        if not use_formatter:
            return _remove_parameters_from_optional_subcomponents(params, ["add_sources"], target_name)

        add_sources = _pop_and_validate_parameter(params, "add_sources", bool, "add_sources must be a boolean")

        formatter = Formatter(
            add_sources=add_sources,
            component_attributes=None,
        )

        params[target_name] = formatter
        return params

    return processor


def compose_processors(*processors: ParameterProcessor) -> ParameterProcessor:
    """
    Composes multiple parameter processors into a single processor.
    Applies processors in order from left to right.
    """

    def composed_processor(params: dict, constructor_params: dict[str, Any]) -> dict:
        result = params
        for processor in processors:
            result = processor(result, constructor_params)
        return result

    return composed_processor


def _pop_and_validate_parameter(params: dict, parameter_name: str, expected_type: type, error_message: str) -> Any:
    """
    Pops a parameter from params dict, validates and converts its type.
    The goal is not rely on running the component to get an error if a parameter coming from the
    front is of a bad type but raise the error directly when trying to save the graph.
    """
    try:
        parameter_value = params.pop(parameter_name)
    except KeyError:
        raise ValueError(f"{error_message}: parameter '{parameter_name}' is required but not found")

    if parameter_value is None:
        raise ValueError(f"{error_message}: parameter '{parameter_name}' cannot be None")

    if expected_type is str:
        if not isinstance(parameter_value, str):
            raise ValueError(f"{error_message}, got {type(parameter_value).__name__}: {parameter_value}")
        return parameter_value

    try:
        parameter_value = expected_type(parameter_value)
    except ValueError as e:
        raise ValueError(f"{error_message}, got {parameter_value}: {e}")
    return parameter_value


def _remove_parameters_from_optional_subcomponents(params: dict, parameters_name: list[str], target_name: str) -> dict:
    for parameter in parameters_name:
        params.pop(parameter, None)
    params[target_name] = None
    return params


def _pop_and_validate_parameters(list_of_params: list[ParameterToValidate], params: dict) -> dict[str, Any]:
    """
    Pops and validates multiple parameters from params dict.
    """
    validated_params = {}
    for param in list_of_params:
        arg = param.argument
        expected_type = param.type
        error_message = f"{arg} must be of type {expected_type.__name__}"
        is_optional = param.optional
        if (not is_optional) or (arg in params and params[arg] is not None):
            validated_params[arg] = _pop_and_validate_parameter(params, arg, expected_type, error_message)
        else:
            params.pop(arg, None)
    return validated_params
