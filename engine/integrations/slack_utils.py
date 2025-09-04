import logging
from typing import Dict, Any
from functools import wraps

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

LOGGER = logging.getLogger(__name__)


def handle_slack_api_errors(func):
    """Decorator to handle Slack API errors"""

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except SlackApiError as e:
            LOGGER.error(f"Error in {func.__name__}: {e.response['error']}")
            raise e

    return wrapper


@handle_slack_api_errors
def send_slack_message(
    client: WebClient,
    channel: str,
    text: str,
    thread_ts: str | None = None,
    attachments: list[Dict[str, str]] | None = None,
) -> Any:
    """Send a message to a Slack channel and thread"""
    result = client.chat_postMessage(
        channel=channel,
        thread_ts=thread_ts,
        text=text,
        attachments=attachments,
    )
    return result
