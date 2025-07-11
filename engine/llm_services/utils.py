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


def filter_unsupported_content_for_chat_completion(
    messages: list[dict[str, Any]] | str,
) -> list[dict[str, Any]] | str:
    """
    Filters out content types that are not supported by standard chat completion APIs.
    
    This function removes file content types and other unsupported content types,
    keeping only text and image_url content types that are supported by most chat completion APIs.
    """
    
    if isinstance(messages, str):
        return messages
    
    filtered_messages = []
    for message in messages:
        if "content" in message and isinstance(message["content"], list) and "role" in message:
            filtered_content = []
            for content in message["content"]:
                if "type" in content:
                    # Keep only supported content types
                    if content["type"] in ["text", "image_url"]:
                        filtered_content.append(content)
                    elif content["type"] == "file":
                        # For now, we'll skip file content as most chat completion APIs don't support it
                        # In the future, this could be enhanced to extract text from files or convert images
                        filename = content.get('file', {}).get('filename', 'unknown')
                        LOGGER.warning(f"Filtering out unsupported file content: {filename}")
                        continue
                    else:
                        # Skip other unsupported content types
                        LOGGER.warning(f"Filtering out unsupported content type: {content['type']}")
                        continue
                else:
                    # If no type specified, assume it's supported
                    filtered_content.append(content)
            
            # If we have any content left, add the message
            if filtered_content:
                message_copy = message.copy()
                message_copy["content"] = filtered_content
                filtered_messages.append(message_copy)
            elif isinstance(message.get("content"), str):
                # If content is a string, keep it as is
                filtered_messages.append(message)
        else:
            # If content is a string or other format, keep it as is
            filtered_messages.append(message)
    
    return filtered_messages


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
