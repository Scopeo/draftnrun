import json
import logging
import time
import uuid
from typing import Any

from openai.types.chat import ChatCompletion, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice

LOGGER = logging.getLogger(__name__)


def convert_tool_messages_to_assistant_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Convert tool messages to assistant messages for response API compatibility.
    Tool messages are not supported in the response API, so we convert them to assistant messages.
    """
    converted_messages = []
    for message in messages:
        role = message.get("role")
        content = message.get("content")
        tool_calls = message.get("tool_calls")

        # Skip assistant messages with None content and non-empty tool_calls
        if role == "assistant" and content is None and tool_calls:
            continue

        # Handle tool messages - convert to assistant messages
        if role == "tool":
            if content is None:
                raise ValueError("Tool message cannot have None content")
            # Convert tool response to assistant message
            # Tool messages are not handled for json_constrained response API call
            assistant_message = {"role": "assistant", "content": content}
            converted_messages.append(assistant_message)
            continue

        # Clean the message by removing tool-related fields
        clean_message = {k: v for k, v in message.items() if k not in ["tool_calls", "tool_call_id"]}
        converted_messages.append(clean_message)

    return converted_messages


def chat_completion_to_response(
    chat_completion_messages: list[dict[str, Any]] | str,
) -> list[dict[str, Any]] | str:
    """
    Converts a chat completion API input to response API input (Openai standards).
    """

    if isinstance(chat_completion_messages, str):
        return chat_completion_messages

    response_messages = chat_completion_messages.copy()

    # Remove tools messages/additional provider api response parameters and make them as assistant messages
    response_messages = convert_tool_messages_to_assistant_messages(response_messages)

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
                    content["type"] = f"{prefix}image"
                    if "image_url" in content and isinstance(content["image_url"], dict):
                        url = content["image_url"].get("url")
                        if url:
                            content["image_url"] = url
        elif "content" in message and isinstance(message["content"], str):
            continue
        else:
            LOGGER.error(f"Error converting to response format: Here is the full payload {chat_completion_messages}")
            raise ValueError(
                (f"Invalid message format: 'content' must be a list or a string. Received: {type(message['content'])}")
            )
    return response_messages


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


def wrap_str_content_into_chat_completion_message(structured_output: str, model_name: str) -> Any:
    """
    Create a fake ChatCompletion object for structured output responses.

    Args:
        structured_output: The structured content to include in the response
        model_name: The model name to include in the response

    Returns:
        A ChatCompletion object with a json structured message
    """
    return ChatCompletion(
        id=f"chatcmpl-{uuid.uuid4()}",
        choices=[
            Choice(
                index=0,
                message=ChatCompletionMessage(role="assistant", content=structured_output),
                finish_reason="stop",
            )
        ],
        created=int(time.time()),
        model=model_name,
        object="chat.completion",
        usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    )


def convert_tool_description_to_output_format(tool_description) -> str:
    """
    Convert ToolDescription to format expected by constrained_complete_with_json_schema_async.

    Args:
        tool_description: The ToolDescription object

    Returns:
        JSON string with name and schema fields that the method expects
    """
    output_format = {
        "name": tool_description.name,
        "schema": {
            "type": "object",
            "properties": tool_description.tool_properties,
            "required": tool_description.required_tool_properties or [],
            "additionalProperties": False,
        },
    }

    return json.dumps(output_format)


def validate_and_extract_json_response(raw_content: str, expected_schema: dict) -> str:
    """
    Validate and extract JSON response data when model returns schema instead of actual data.

    Some models return the schema structure instead of the actual data values.
    This function checks if the response matches the expected schema structure
    and extracts just the data properties if so.

    Args:
        raw_content: The raw response content from the LLM
        expected_schema: The expected schema structure with properties

    Returns:
        JSON string with just the data properties if schema was returned, otherwise original content
    """
    try:
        parsed_response = json.loads(raw_content)
        if "properties" in parsed_response:
            response_properties = parsed_response["properties"]
            expected_properties = expected_schema.get("properties", {})

            # Check if the response contains the same properties as expected schema
            if set(response_properties.keys()) == set(expected_properties.keys()):
                # Return just the data properties, not the full schema
                return json.dumps(response_properties, ensure_ascii=False)
        return raw_content

    except (json.JSONDecodeError, TypeError, AttributeError):
        LOGGER.error(f"Error validating JSON response format: {raw_content}")
        return raw_content


async def get_structured_response_without_tools(
    completion_service,
    structured_output_tool,
    messages: list[dict] | str,
    stream: bool = False,
) -> Any:
    """
    Get a structured response when explicitly choosing to answer without tools (tool_choice="none").

    Args:
        completion_service: The completion service instance
        structured_output_tool: The structured output tool description
        messages: The messages to send to the LLM
        stream: Whether to stream the response

    Returns:
        A ChatCompletion object with the structured content
    """
    LOGGER.info("Getting structured response without tools using LLM constrained method")
    structured_json_output = convert_tool_description_to_output_format(structured_output_tool)
    structured_content = await completion_service.constrained_complete_with_json_schema_async(
        messages=messages,
        stream=stream,
        response_format=structured_json_output,
    )
    response = wrap_str_content_into_chat_completion_message(structured_content, completion_service._model_name)
    return response


async def ensure_structured_output_response(response, structured_output_tool, completion_service, stream):
    """
    Ensure the response is formatted as structured output.

    If the structured output tool was called, extract its result.
    If no tools were called, use backup LLM method to force structured formatting.

    Args:
        response: The ChatCompletion response object to modify
        structured_output_tool: The structured output tool description
        completion_service: The completion service instance
        stream: Whether to stream the response

    Returns:
        A ChatCompletion object with structured content
    """
    tools_called = response.choices[0].message.tool_calls
    if not tools_called:
        LOGGER.error("No tools were called in the response, using backup llm method to format the answer")
        content = response.choices[0].message.content
        # If content is None, we can't use it as messages, so we need to handle this case
        if content is None:
            LOGGER.error("Response content is None, cannot format structured output")
            raise ValueError("Cannot format structured output: response content is None as well as tools called")
        response = await get_structured_response_without_tools(
            completion_service=completion_service,
            structured_output_tool=structured_output_tool,
            messages=content,
            stream=stream,
        )
        return response

    for call in tools_called:
        if call.function.name == structured_output_tool.name:
            # Return the arguments of the structured output tool as the final response
            # Discard the other tool call results
            try:
                response.choices[0].message.content = json.dumps(call.function.arguments, ensure_ascii=False)
                response.choices[0].message.tool_calls = None
                return response
            except Exception as e:
                raise ValueError(f"Error parsing structured output tool response with error {e}")
    return response
