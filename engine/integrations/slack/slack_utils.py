import logging
from functools import wraps

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from slack_sdk.web import SlackResponse

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
    as_markdown: bool = False,
    thread_ts: str | None = None,
    attachments: list[dict[str, str]] | None = None,
) -> SlackResponse:
    result = client.chat_postMessage(
        channel=channel,
        thread_ts=thread_ts,
        attachments=attachments,
        text=text if not as_markdown else None,
        markdown_text=text if as_markdown else None,
    )
    return result
