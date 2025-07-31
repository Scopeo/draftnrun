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


def get_slack_client(access_token: str) -> WebClient:
    """Create a Slack WebClient with the provided OAuth access token"""
    return WebClient(token=access_token)


@handle_slack_api_errors
def send_slack_message(
    client: WebClient,
    channel: str,
    text: str,
    thread_ts: str | None = None,
    attachments: list[Dict[str, str]] | None = None,
) -> Dict[str, Any]:
    """Send a message to a Slack channel and thread"""
    result = client.chat_postMessage(
        channel=channel,
        thread_ts=thread_ts,
        text=text,
        attachments=attachments,
    )
    return result


@handle_slack_api_errors
def get_channel_info(client: WebClient, channel_id: str) -> Dict[str, Any]:
    """Get information about a Slack channel"""
    result = client.conversations_info(channel=channel_id)
    return result["channel"]


@handle_slack_api_errors
def get_user_info(client: WebClient, user_id: str) -> Dict[str, Any]:
    """Get information about a Slack user"""
    result = client.users_info(user=user_id)
    return result["user"]


@handle_slack_api_errors
def get_channels_where_bot_is(client: WebClient) -> list[str]:
    """Returns a list of channel IDs where the bot is a member"""
    result = client.conversations_list()
    channels = result["channels"]
    channels = [channel["id"] for channel in channels if channel["is_member"]]
    return channels


@handle_slack_api_errors
def get_channel_name(client: WebClient, channel_id: str) -> str:
    """Returns a channel name given a channel ID"""
    result = client.conversations_info(channel=channel_id)
    return result["channel"]["name"]


@handle_slack_api_errors
def is_inbox_channel(client: WebClient, channel_id: str) -> bool:
    """Check if a channel is a direct message (inbox)"""
    response = client.conversations_info(channel=channel_id, include_num_members=True)
    is_inbox = response.data["channel"]["is_im"]
    return is_inbox


@handle_slack_api_errors
def send_image(
    client: WebClient,
    image_file: str,
    initial_comment: str,
    alt_txt: str,
    channel_id: str,
    thread_ts: str | None = None,
) -> Dict[str, Any]:
    """Send an image to a Slack channel and thread"""
    with open(image_file, "rb") as file:
        result = client.files_upload_v2(
            initial_comment=initial_comment,
            alt_txt=alt_txt,
            channel=channel_id,
            thread_ts=thread_ts,
            file=file,
        )
    return result
