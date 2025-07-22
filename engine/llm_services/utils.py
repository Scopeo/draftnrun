import logging
from typing import Any

from ada_backend.services.trace_service import TOKEN_LIMIT, get_token_usage
from engine.trace.span_context import get_tracing_span


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


def make_messages_compatible_for_mistral(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Make messages compatible for Mistral API by removing tool-related
    fields from message types that don't support them.

    Mistral only allows:
    - tool_calls in assistant messages
    - tool_call_id in tool messages
    """
    if not isinstance(messages, list):
        return messages

    mistral_compatible_messages = []
    for message in messages:
        mistral_compatible_message = message.copy()
        role = message.get("role")

        # Remove tool_calls from non-assistant messages
        if role != "assistant" and "tool_calls" in mistral_compatible_message:
            del mistral_compatible_message["tool_calls"]

        # Remove tool_call_id from non-tool messages
        if role != "tool" and "tool_call_id" in mistral_compatible_message:
            del mistral_compatible_message["tool_call_id"]

        # Remove None values to avoid sending empty fields
        mistral_compatible_message = {k: v for k, v in mistral_compatible_message.items() if v is not None}

        mistral_compatible_messages.append(mistral_compatible_message)

    return mistral_compatible_messages


class LLMKeyLimitExceededError(Exception):
    pass


def check_usage(provider: str) -> None:
    tracing_span_params = get_tracing_span()
    if provider not in tracing_span_params.organization_llm_providers:
        LOGGER.info(
            f"LLM provider '{provider}' is not configured for the organization. " "Checking organization token usage."
        )
        token_usage = get_token_usage(organization_id=tracing_span_params.organization_id)
        if token_usage.total_tokens > TOKEN_LIMIT:
            raise LLMKeyLimitExceededError(
                f"You are currently using Draft'n run's default {provider} LLM key, "
                "which has exceeded its token limit. "
                "Please provide your own key."
            )
    return None
