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
                        if "file" in content and isinstance(content["file"], dict):
                            content.update(content["file"])
                            del content["file"]
                        content["type"] = f"{prefix}file"
                    else:
                        content["type"] = f"{prefix}{content['type']}"
                elif "type" in content and content["type"] == "image_url":
                    # For image_url, convert to input_image format expected by response API
                    content["type"] = f"{prefix}image"
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


def make_mistral_ocr_compatible(payload_json: dict) -> list[dict]:

    if "messages" not in payload_json or not payload_json["messages"]:
        return None

    for message in reversed(payload_json["messages"]):
        if not isinstance(message, dict) or "content" not in message:
            continue

        content = message["content"]
        if not content:
            continue

        payload_json["messages"][-1]["content"] = content if isinstance(content, list) else [content]

        for content_item in payload_json["messages"][-1]["content"]:
            if (
                isinstance(content_item, dict)
                and "file" in content_item
                and isinstance(content_item["file"], dict)
                and "file_data" in content_item["file"]
            ):
                return {
                    "type": "document_url",
                    "document_url": content_item["file"]["file_data"],
                }
            elif (
                isinstance(content_item, dict)
                and "image_url" in content_item
                and isinstance(content_item["image_url"], dict)
                and "url" in content_item["image_url"]
            ):
                return {
                    "type": "image_url",
                    "image_url": content_item["image_url"]["url"],
                }

    return None


# TODO: Quick fix for GPT-5 models, remove when we have better solution
def build_openai_responses_kwargs(
    model_name: str,
    verbosity: str | None,
    reasoning: str | None,
    temperature: float | None,
    base_kwargs: dict,
) -> dict:
    """
    Return kwargs for OpenAI Responses API, adding verbosity/reasoning only for GPT-5 models.
    """
    kwargs = dict(base_kwargs)
    is_gpt5 = "gpt-5" in (model_name or "").lower()
    if is_gpt5:
        if verbosity is not None:
            kwargs["text"] = {"verbosity": verbosity}
        if reasoning is not None:
            kwargs["reasoning"] = {"effort": reasoning}
        if temperature is not None:
            LOGGER.info(f"Temperature set to 1 for the {model_name} model.")
            kwargs["temperature"] = 1
    return kwargs
