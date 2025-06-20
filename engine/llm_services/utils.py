import logging
from typing import Any

from ada_backend.services.trace_service import TOKEN_LIMIT, get_token_usage
from engine.trace.trace_context import get_trace_manager


LOGGER = logging.getLogger(__name__)


def chat_completion_to_response(
    chat_completion_messages: list[dict[str, Any]] | str,
) -> list[dict[str, Any]] | str:
    """
    Converts a chat completion API input to response API input (Openai standards).
    """

    if isinstance(chat_completion_messages, str):
        return chat_completion_messages

    response_messages = chat_completion_messages.copy()
    for message in response_messages:
        if "content" in message and isinstance(message["content"], list) and "role" in message:
            prefix = "output_" if message["role"] == "assistant" else "input_"
            for content in message["content"]:
                if "type" in content and content["type"] in ["text", "image", "file"]:
                    if content["type"] == "file":
                        content.update(content["file"])
                        del content["file"]
                    content["type"] = f"{prefix}{content['type']}"
        elif "content" in message and isinstance(message["content"], str):
            continue
        else:
            LOGGER.error(f"Error converting to response format: Here is the full payload {chat_completion_messages}")
            raise ValueError(
                (
                    "Invalid message format: 'content' must be a list or a string."
                    f" Received: {type(message['content'])}"
                )
            )
    return response_messages


class LLMKeyLimitExceededError(Exception):
    pass


def check_usage(provider: str) -> None:
    trace_manager = get_trace_manager()
    if provider not in trace_manager.organization_llm_providers:
        LOGGER.info(
            f"LLM provider '{provider}' is not configured for the organization. " "Checking organization token usage."
        )
        token_usage = get_token_usage(organization_id=trace_manager.organization_id)
        if token_usage.total_tokens > TOKEN_LIMIT:
            raise LLMKeyLimitExceededError(
                f"You are currently using Draft'n run's default {provider} LLM key, "
                "which has exceeded its token limit. "
                "Please provide your own key."
            )
    return None
