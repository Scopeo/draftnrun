"""
OpenAI-specific streaming utilities.

These helper functions consume OpenAI streaming responses and return
the same format as non-streaming calls for backward compatibility.
"""

import logging
from typing import Any

from pydantic import BaseModel

LOGGER = logging.getLogger(__name__)


async def consume_openai_responses_stream(
    stream: Any,
) -> tuple[str, int, int, int]:
    """
    Consume OpenAI responses.create stream and return accumulated text with token counts.

    Args:
        stream: Stream from client.responses.create(stream=True)

    Returns:
        Tuple of (accumulated_text, input_tokens, output_tokens, total_tokens)
    """
    accumulated_text = ""
    final_response = None

    async for event in stream:
        event_type = getattr(event, "type", None)

        # Accumulate text deltas
        if event_type and "output_text" in event_type:
            if hasattr(event, "delta") and event.delta:
                accumulated_text += event.delta
            elif hasattr(event, "text") and event.text:
                accumulated_text += event.text

        # Capture final response for usage extraction
        if event_type == "response.done" or event_type == "done":
            if hasattr(event, "response") and event.response:
                final_response = event.response

    # Extract usage tokens
    if final_response:
        input_tokens = final_response.usage.input_tokens
        output_tokens = final_response.usage.output_tokens
        total_tokens = final_response.usage.total_tokens
    else:
        input_tokens, output_tokens, total_tokens = 0, 0, 0

    return accumulated_text, input_tokens, output_tokens, total_tokens


async def consume_openai_responses_stream_and_get_final_response(
    stream_context: Any,
) -> Any:
    """
    Consume OpenAI responses.stream() context manager and return final response object.

    This function works with client.responses.stream() which returns a context manager
    that yields streaming events and provides get_final_response() for the complete result.

    Args:
        stream_context: Context manager from client.responses.stream()

    Returns:
        Final response object from OpenAI (same structure as non-streaming response)
    """
    # Consume all events (the context manager handles iteration)
    async for event in stream_context:
        # Just consume events; we'll get the final response at the end
        pass

    # Get the final response with all accumulated data (await if it's a coroutine)
    final_response = stream_context.get_final_response()
    if hasattr(final_response, "__await__"):
        final_response = await final_response

    return final_response


def extract_openai_text_result(response: Any) -> str:
    """
    Extract text result from an OpenAI response object.

    Args:
        response: OpenAI response object (from responses.create or responses.stream)

    Returns:
        Text output from the response
    """
    if hasattr(response, "output_text"):
        return response.output_text
    return str(response)


def extract_openai_parsed_result(response: Any) -> BaseModel | str:
    """
    Extract parsed result from an OpenAI response object.

    Args:
        response: OpenAI response object (from responses.parse or responses.stream)

    Returns:
        Parsed output (BaseModel) or text output as fallback
    """
    if hasattr(response, "output_parsed") and response.output_parsed is not None:
        return response.output_parsed
    elif hasattr(response, "output_text"):
        return response.output_text
    return str(response)


async def consume_openai_responses_stream_context_manager(
    stream_context: Any,
) -> tuple[BaseModel | str, int, int, int]:
    """
    Consume OpenAI responses.stream() context manager and return final response.

    This function works with client.responses.stream() which returns a context manager
    that yields streaming events and provides get_final_response() for the complete result.

    Args:
        stream_context: Context manager from client.responses.stream()

    Returns:
        Tuple of (parsed_output_or_text, input_tokens, output_tokens, total_tokens)
    """
    final_response = await consume_openai_responses_stream_and_get_final_response(stream_context)
    result = extract_openai_parsed_result(final_response)
    input_tokens = final_response.usage.input_tokens
    output_tokens = final_response.usage.output_tokens
    total_tokens = final_response.usage.total_tokens

    return result, input_tokens, output_tokens, total_tokens
