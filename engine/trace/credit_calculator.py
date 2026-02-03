import ast
import logging
from functools import wraps
from typing import Any, Callable, Optional

from opentelemetry.trace import Span

from ada_backend.services.credits_service import (
    get_component_cost_for_calculation_service,
    get_llm_cost_for_calculation_service,
)
from engine.trace.sql_exporter import trace_session

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

            with trace_session() as session:
                cost_info = get_llm_cost_for_calculation_service(session, self._model_id)

                if cost_info and (cost_info.credits_per_input_token or cost_info.credits_per_output_token):
                    credits_input_token = prompt_tokens * (cost_info.credits_per_input_token or 0) / 1_000_000
                    credits_output_token = (
                        completion_tokens_value * (cost_info.credits_per_output_token or 0) / 1_000_000
                    )

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

        with trace_session() as session:
            cost_info = get_component_cost_for_calculation_service(session, component_instance_id)

            if cost_info and cost_info.credits_per_call:
                span.set_attributes({"credits.per_call": cost_info.credits_per_call})
                LOGGER.debug(f"Component credits calculated: per_call={cost_info.credits_per_call}")

    except Exception as e:
        LOGGER.error(f"Error calculating component credits: {e}", exc_info=True)
