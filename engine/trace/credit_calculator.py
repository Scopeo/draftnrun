import ast
import logging
from functools import wraps
from typing import Any, Callable, Optional
from uuid import UUID

from cachetools import TTLCache, cached
from opentelemetry.trace import Span

from ada_backend.context import get_request_context
from ada_backend.database.setup_db import get_db_session
from ada_backend.repositories.credits_repository import get_component_cost_per_call, get_llm_cost

LOGGER = logging.getLogger(__name__)


_llm_cost_cache: TTLCache[tuple[UUID, UUID], tuple[Optional[float], Optional[float]]] = TTLCache(maxsize=1000, ttl=300)

_component_cost_cache: TTLCache[tuple[UUID, UUID], Optional[float]] = TTLCache(maxsize=1000, ttl=300)


def _fetch_from_db(repository_func: Callable, *args, resource_name: str, **kwargs) -> Any:
    try:
        context = get_request_context()
        LOGGER.info(f"Fetching {resource_name} in request_id {context.request_id}")
    except (ValueError, LookupError):
        LOGGER.info(f"No request context available, fetching {resource_name} without caching")

    with get_db_session() as session:
        return repository_func(session, *args, **kwargs)


@cached(cache=_llm_cost_cache, key=lambda model_id: (get_request_context().request_id, model_id))
def get_cached_llm_cost(model_id: UUID) -> tuple[Optional[float], Optional[float]]:
    return _fetch_from_db(get_llm_cost, model_id, resource_name=f"LLM cost for model_id {model_id}")


@cached(
    cache=_component_cost_cache,
    key=lambda component_instance_id: (get_request_context().request_id, component_instance_id),
)
def get_cached_component_cost(component_instance_id: UUID) -> Optional[float]:
    return _fetch_from_db(
        get_component_cost_per_call,
        component_instance_id,
        resource_name=f"component cost for component_instance_id {component_instance_id}",
    )


def convert_to_list(obj: Any) -> list[str] | None:
    """Convert object to list of strings if possible."""
    if isinstance(obj, list):
        return obj
    if isinstance(obj, tuple):
        return list(obj)
    if obj is None:
        return None
    if isinstance(obj, str):
        try:
            result = ast.literal_eval(obj)
            if isinstance(result, (list, tuple)):
                return list(result)
        except (ValueError, SyntaxError):
            pass
    return None


def calculate_llm_credits(func: Callable) -> Callable:
    """Decorator to calculate and set LLM credits on span after setting token counts."""

    @wraps(func)
    def wrapper(self, span, prompt_tokens: int, completion_tokens: Optional[int], total_tokens: int):
        func(self, span, prompt_tokens, completion_tokens, total_tokens)

        if not self._model_id:
            return

        try:
            org_llm_providers = convert_to_list(span.attributes.get("organization_llm_providers"))
            if self._provider and org_llm_providers and self._provider in org_llm_providers:
                LOGGER.debug(
                    f"Provider {self._provider} is in organization_llm_providers, skipping credit calculation"
                )
                return

            completion_tokens_value = completion_tokens if completion_tokens is not None else 0

            credits_per_input_token, credits_per_output_token = get_cached_llm_cost(self._model_id)
            if credits_per_input_token and credits_per_output_token:
                credits_input_token = prompt_tokens * credits_per_input_token / 1_000_000
                credits_output_token = completion_tokens_value * credits_per_output_token / 1_000_000

                span.set_attributes({
                    "credits.input_token": credits_input_token,
                    "credits.output_token": credits_output_token,
                })
                LOGGER.info(f"LLM credits calculated: input={credits_input_token}, output={credits_output_token}")
            else:
                LOGGER.info(f"No cost info found for model_id {self._model_id}")

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
