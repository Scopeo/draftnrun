import logging
from tenacity import AsyncRetrying, retry_if_exception_type, wait_random_exponential, stop_after_attempt

LOGGER = logging.getLogger(__name__)


# Retry decorator for async methods
def async_retry(*, wait=None, stop=None, retry=retry_if_exception_type(Exception)):
    def decorator(func):
        async def wrapper(*args, **kwargs):
            async for attempt in AsyncRetrying(wait=wait, stop=stop, retry=retry, reraise=True):
                with attempt:
                    return await func(*args, **kwargs)

        return wrapper

    return decorator


def chat_completion_to_response(
    chat_completion_messages: list[dict[str]],
) -> list[dict[str]]:
    """
    Converts a chat completion API input to response API input (Openai standards).
    """
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
