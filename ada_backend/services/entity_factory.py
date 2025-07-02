import logging
import json
import inspect
from inspect import signature
from typing import Optional, Any, Type, Callable, get_type_hints, get_origin, get_args, Union
from uuid import UUID
from dataclasses import is_dataclass
from pydantic import BaseModel

from engine.agent.agent import ToolDescription
from engine.trace.trace_context import get_trace_manager
from engine.llm_services.llm_service import EmbeddingService, CompletionService, WebSearchService
from engine.qdrant_service import QdrantService, QdrantCollectionSchema

from ada_backend.database.setup_db import get_async_db_session
from ada_backend.repositories.source_repository import get_data_source_by_id

LOGGER = logging.getLogger(__name__)

ParameterProcessor = Callable[[dict, dict[str, Any]], Any]


class EntityFactory:
    def __init__(
        self,
        entity_class: Type[Any],
        parameter_processors: Optional[list[ParameterProcessor]] = None,
        constructor_method: str = "__init__",
    ):
        self.entity_class = entity_class
        self.constructor_method = constructor_method
        self.parameter_processors = parameter_processors or []
        self.constructor_params = self._get_constructor_params()

    def _get_constructor_params(self) -> dict[str, Any]:
        if not hasattr(self.entity_class, self.constructor_method):
            raise ValueError(f"{self.entity_class.__name__} does not have a method named '{self.constructor_method}'.")
        method = getattr(self.entity_class, self.constructor_method)
        if not callable(method):
            raise ValueError(f"'{self.constructor_method}' is not callable on {self.entity_class.__name__}.")
        hints = get_type_hints(method)
        params = signature(method).parameters
        return {
            name: hints.get(name, param.annotation)
            for name, param in params.items()
            if param.annotation is not param.empty
        }

    async def _process_parameters(self, *args, **kwargs) -> tuple[tuple, dict]:
        for processor in self.parameter_processors:
            if inspect.iscoroutinefunction(processor):
                kwargs = await processor(kwargs, self.constructor_params)
            else:
                kwargs = processor(kwargs, self.constructor_params)
        return args, kwargs

    async def __call__(self, *args, **kwargs) -> Any:
        args, kwargs = await self._process_parameters(*args, **kwargs)
        if self.constructor_method == "__init__":
            return self.entity_class(*args, **kwargs)
        constructor_method = getattr(self.entity_class, self.constructor_method, None)
        if not callable(constructor_method):
            raise ValueError(f"Method '{self.constructor_method}' is not callable on {self.entity_class.__name__}.")
        return constructor_method(*args, **kwargs)


class AgentFactory(EntityFactory):
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

    async def _process_parameters(self, *args, **kwargs) -> tuple[tuple, dict]:
        args, kwargs = await super()._process_parameters(*args, **kwargs)
        tool_description = kwargs.get("tool_description")
        if not isinstance(tool_description, ToolDescription):
            raise ValueError("Tool description must be a ToolDescription object.")
        return args, kwargs


# These functions remain sync as they do not perform I/O


def build_dataclass_processor(dataclass_type: Type[Any], param_name: str) -> ParameterProcessor:
    def processor(params: dict, constructor_params: dict[str, Any]) -> dict:
        if param_name in params and not isinstance(params[param_name], dataclass_type):
            try:
                data = params[param_name]
                if isinstance(data, str):
                    data = json.loads(data)
                LOGGER.debug(f"Converting {param_name} with data: {data}")
                params[param_name] = dataclass_type(**data)
            except Exception as e:
                LOGGER.error(f"Error converting {param_name} to {dataclass_type.__name__}: {e}")
                raise e
        return params

    return processor


def detect_and_convert_dataclasses(params: dict, constructor_params: dict[str, Any]) -> dict:
    for param_name, param_type in constructor_params.items():
        if get_origin(param_type) is Union:
            param_type = next((arg for arg in get_args(param_type) if is_dataclass(arg)), None)
        if param_name in params and param_type and is_dataclass(param_type):
            processor = build_dataclass_processor(param_type, param_name)
            params = processor(params, constructor_params)
    return params


def pydantic_processor(params: dict, constructor_params: dict[str, Any]) -> dict:
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
    def translator(params: dict, constructor_params: dict[str, Any]) -> dict:
        for external_name, internal_name in mapping.items():
            if external_name in params and internal_name not in params:
                params[internal_name] = params.pop(external_name)
        return params

    return translator


def get_llm_provider_and_model(llm_model: str) -> tuple[str, str]:
    if ":" not in llm_model:
        raise ValueError(f"Invalid LLM model format: {llm_model}. Expected 'provider:model_name'.")
    parts = llm_model.split(":")
    if len(parts) == 2:
        provider, model = parts
    else:
        raise ValueError(f"Format invalide pour llm_model: {llm_model}")
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

        completion_service = CompletionService(
            provider=provider,
            model_name=model_name,
            trace_manager=get_trace_manager(),
            temperature=params.pop("temperature", 0.5),
            api_key=params.pop("llm_api_key", None),
        )

        params[target_name] = completion_service
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

        web_service = WebSearchService(
            trace_manager=get_trace_manager(),
            provider=provider,
            model_name=model_name,
            api_key=params.pop("llm_api_key", None),
        )

        params[target_name] = web_service
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

    async def processor(params: dict, constructor_params: dict[str, Any]) -> dict:
        source_id_str: str = params.pop("data_source")["id"]
        if not source_id_str:
            raise ValueError("data_source_id is required")
        source_id = UUID(source_id_str)

        # TODO: Temporary solution - needs proper session injection in future refactor.
        async with get_async_db_session() as session:
            source = await get_data_source_by_id(session, source_id)
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


def compose_processors(*processors: ParameterProcessor) -> ParameterProcessor:
    """
    Composes multiple parameter processors into a single processor.
    Applies processors in order from left to right.
    """

    async def composed_processor(params: dict, constructor_params: dict[str, Any]) -> dict:
        result = params
        for processor in processors:
            if inspect.iscoroutinefunction(processor):
                result = await processor(result, constructor_params)
            else:
                maybe = processor(result, constructor_params)
                result = await maybe if inspect.isawaitable(maybe) else maybe
        return result

    return composed_processor
