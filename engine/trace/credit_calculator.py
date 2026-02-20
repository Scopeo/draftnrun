import logging
from functools import wraps
from typing import Any, Callable, Optional
from uuid import UUID

from cachetools import TTLCache, cached
from opentelemetry.trace import Span

from ada_backend.context import get_execution_id
from ada_backend.database.setup_db import get_db_session
from ada_backend.repositories.credits_repository import get_component_cost_per_call, get_llm_cost

LOGGER = logging.getLogger(__name__)

_llm_cost_cache: TTLCache[tuple[UUID, UUID], tuple[Optional[float], Optional[float]]] = TTLCache(maxsize=1000, ttl=300)

_component_cost_cache: TTLCache[tuple[UUID, UUID], Optional[float]] = TTLCache(maxsize=1000, ttl=300)


def _fetch_from_db_with_managed_session(repository_func: Callable, *args, resource_name: str, **kwargs) -> Any:
    try:
        execution_id = get_execution_id()
        LOGGER.info(f"Fetching {resource_name} in execution_id {execution_id}")
    except (ValueError, LookupError):
        LOGGER.info(f"No execution context available, fetching {resource_name} without caching")

    with get_db_session() as session:
        return repository_func(session, *args, **kwargs)


def _llm_cost_cache_key(model_id: UUID) -> tuple[UUID, UUID]:
    try:
        return (get_execution_id(), model_id)
    except (ValueError, LookupError):
        LOGGER.warning("No execution context for LLM cost cache, skipping cache")
        return (object(), model_id)


def _component_cost_cache_key(component_instance_id: UUID) -> tuple[UUID, UUID]:
    try:
        return (get_execution_id(), component_instance_id)
    except (ValueError, LookupError):
        LOGGER.warning("No execution context for component cost cache, skipping cache")
        return (object(), component_instance_id)


# TODO: Optimize LLM cost fetching to reduce DB calls
@cached(cache=_llm_cost_cache, key=_llm_cost_cache_key)
def get_cached_llm_cost(model_id: UUID) -> tuple[Optional[float], Optional[float]]:
    return _fetch_from_db_with_managed_session(
        get_llm_cost, model_id, resource_name=f"LLM cost for model_id {model_id}"
    )


# TODO: Optimize component cost fetching to reduce DB calls
# Current implementation: 1 DB call per request per component (cached per request)
# Potential optimizations:
#   1. Fetch all component costs for the current workflow
#   2. Fetch all component definitions with grouping
@cached(cache=_component_cost_cache, key=_component_cost_cache_key)
def get_cached_component_cost(component_instance_id: UUID) -> Optional[float]:
    return _fetch_from_db_with_managed_session(
        get_component_cost_per_call,
        component_instance_id,
        resource_name=f"component cost for component_instance_id {component_instance_id}",
    )


def calculate_llm_credits(func: Callable) -> Callable:
    """Decorator to calculate and set LLM credits on span after setting token counts."""

    @wraps(func)
    def wrapper(self, span, prompt_tokens: int, completion_tokens: Optional[int], total_tokens: int):
        func(self, span, prompt_tokens, completion_tokens, total_tokens)

        if not self._model_id:
            return

        try:
            completion_tokens_value = completion_tokens if completion_tokens is not None else 0

            credits_per_input_token, credits_per_output_token = get_cached_llm_cost(self._model_id)

            attributes = {}
            if credits_per_input_token is not None:
                credits_input_token = prompt_tokens * credits_per_input_token / 1_000_000
                attributes["credits.input_token"] = credits_input_token

            if credits_per_output_token is not None:
                credits_output_token = completion_tokens_value * credits_per_output_token / 1_000_000
                attributes["credits.output_token"] = credits_output_token

            if attributes:
                attributes["provider"] = self._provider
                span.set_attributes(attributes)
                LOGGER.info(f"LLM credits calculated: {attributes}")
            else:
                LOGGER.warning(f"No cost info found for model_id {self._model_id}")

        except Exception as e:
            LOGGER.error(f"Error calculating LLM credits: {e}", exc_info=True)

    return wrapper


def calculate_and_set_component_credits(span: Span) -> None:
    """Calculate and set component credits on span based on component instance cost."""
    try:
        component_instance_id = span.attributes.get("component_instance_id")
        if not component_instance_id:
            return

        credits_per_call = get_cached_component_cost(component_instance_id)
        if credits_per_call:
            span.set_attributes({"credits.per_call": credits_per_call})
            LOGGER.info(f"Component credits calculated: per_call={credits_per_call}")
    except Exception as e:
        LOGGER.error(f"Error calculating component credits: {e}", exc_info=True)
