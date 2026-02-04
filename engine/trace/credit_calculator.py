import ast
import logging
from functools import wraps
from typing import Any, Callable, Optional

from opentelemetry.trace import Span

from ada_backend.database.setup_db import get_db_session
from ada_backend.repositories.credits_repository import (
    get_component_cost_for_calculation,
    get_llm_cost_for_calculation,
)

LOGGER = logging.getLogger(__name__)


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

            with get_db_session() as session:
                credits_per_input_token, credits_per_output_token = get_llm_cost_for_calculation(
                    session, self._model_id
                )
                if credits_per_input_token and credits_per_output_token:
                    credits_input_token = prompt_tokens * credits_per_input_token / 1_000_000
                    credits_output_token = completion_tokens_value * credits_per_output_token / 1_000_000

                    span.set_attributes({
                        "credits.input_token": credits_input_token,
                        "credits.output_token": credits_output_token,
                    })
                    LOGGER.debug(f"LLM credits calculated: input={credits_input_token}, output={credits_output_token}")
                else:
                    LOGGER.debug(f"No cost info found for model_id {self._model_id}")

        except Exception as e:
            LOGGER.error(f"Error calculating LLM credits: {e}", exc_info=True)

    return wrapper


def calculate_and_set_component_credits(span: Span) -> None:
    """Calculate and set component credits on span based on component instance cost."""
    try:
        component_instance_id = span.attributes.get("component_instance_id")
        if not component_instance_id:
            return

        with get_db_session() as session:
            credits_per_call = get_component_cost_for_calculation(session, component_instance_id)

            if credits_per_call:
                span.set_attributes({"credits.per_call": credits_per_call})
                LOGGER.debug(f"Component credits calculated: per_call={credits_per_call}")

    except Exception as e:
        LOGGER.error(f"Error calculating component credits: {e}", exc_info=True)
