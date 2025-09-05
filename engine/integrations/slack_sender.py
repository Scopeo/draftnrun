import logging
from typing import Optional

from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
from opentelemetry.trace import get_current_span
from slack_sdk import WebClient

from engine.agent.types import AgentPayload, ChatMessage, ComponentAttributes, ToolDescription
from engine.agent.agent import Agent
from engine.integrations.slack_utils import send_slack_message
from engine.trace.trace_manager import TraceManager

LOGGER = logging.getLogger(__name__)

SLACK_SENDER_TOOL_DESCRIPTION = ToolDescription(
    name="Slack Sender",
    description="A tool to send messages to Slack channels using OAuth integration.",
    tool_properties={
        "channel": {
            "type": "string",
            "description": (
                "Channel name or ID to send message to (e.g., #general or C1234567890). "
                "If unspecified, leave it blank: it will fallback to a default channel."
            ),
        },
        "message": {
            "type": "string",
            "description": "Message text to send to the channel",
        },
        "thread_ts": {
            "type": "string",
            "description": "Thread timestamp to reply to (optional). If provided, message will be sent as a reply.",
        },
    },
    required_tool_properties=["message"],
)


class SlackSender(Agent):
    """Slack integration component for sending messages to Slack channels using OAuth."""

    TRACE_SPAN_KIND = OpenInferenceSpanKindValues.TOOL.value

    def __init__(
        self,
        trace_manager: TraceManager,
        component_attributes: ComponentAttributes,
        access_token: str,
        default_channel: Optional[str] = None,
        tool_description: ToolDescription = SLACK_SENDER_TOOL_DESCRIPTION,
    ):
        """Initialize SlackSender with a provided Slack OAuth access token.

        Args:
            trace_manager: Trace manager for observability
            component_attributes: Component configuration attributes
            access_token: Slack OAuth access token (already obtained via OAuth flow)
            default_channel: Default Slack channel for messages
            tool_description: Tool description for the agent
        """
        super().__init__(
            trace_manager,
            tool_description=tool_description,
            component_attributes=component_attributes,
        )

        self.client = WebClient(token=access_token)
        self.default_channel = default_channel

    async def _run_without_io_trace(  # type: ignore[override]
        self,
        *inputs: AgentPayload,
        channel: Optional[str] = None,
        message: Optional[str] = None,
        thread_ts: Optional[str] = None,
    ) -> AgentPayload:
        """Send a message to a Slack channel.

        Args:
            *inputs: Input payloads (not used for this component)
            **kwargs: Expected keys: channel, message, thread_ts (optional)

        Returns:
            AgentPayload: Success response with message details

        Raises:
            ValueError: If message or channel is not provided
            RuntimeError: If message sending fails
        """
        if not message:
            raise ValueError("Message must be provided")

        target_channel = channel or self.default_channel
        if not target_channel:
            raise ValueError("Channel must be provided either as parameter or default")

        span = get_current_span()
        span.set_attributes(
            {
                SpanAttributes.INPUT_VALUE: f"Channel: {target_channel}\nMessage: {message}",
            }
        )

        try:
            LOGGER.info(f"Sending message to Slack channel {target_channel}")
            result = send_slack_message(
                client=self.client,
                channel=target_channel,
                text=message,
                thread_ts=thread_ts,
                as_markdown=True,
            )

            output_message = f"Message sent successfully to {target_channel}. Timestamp: {result['ts']}"
            if thread_ts:
                output_message += f" (in thread {thread_ts})"

            LOGGER.info(f"Slack message sent successfully: {result['ts']}")

            return AgentPayload(messages=[ChatMessage(role="assistant", content=output_message)])

        except Exception as e:
            error_msg = f"Failed to send Slack message: {e}"
            LOGGER.error(error_msg)
            raise RuntimeError(error_msg) from e
