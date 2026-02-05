import logging
from typing import Optional, Type

from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
from opentelemetry.trace import get_current_span
from pydantic import BaseModel, Field
from slack_sdk import WebClient

from engine.components.component import Component
from engine.components.types import ComponentAttributes, ToolDescription
from engine.integrations.slack.slack_utils import send_slack_message
from engine.trace.serializer import serialize_to_json
from engine.trace.trace_manager import TraceManager

LOGGER = logging.getLogger(__name__)

SLACK_SENDER_TOOL_DESCRIPTION = ToolDescription(
    name="Slack Sender",
    description="A tool to send messages to Slack channels using OAuth integration.",
    tool_properties={
        "channel": {
            "type": "string",
            "description": "Channel name or ID to send message to (e.g., #general or C1234567890).",
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
    required_tool_properties=["channel", "message"],
)


class SlackSenderInputs(BaseModel):
    channel: str = Field(description="Channel name or ID to send message to (e.g., #general or C1234567890).")
    message: str = Field(description="Message text to send to the channel")
    thread_ts: Optional[str] = Field(
        default=None,
        description=(
            "Thread timestamp to reply to a specific message (optional). "
            "Format: '1234567890.123456' - found in the message URL after 'p' with a dot before the last 6 digits. "
            "Example: from URL 'https://workspace.slack.com/archives/C123/p1234567890123456' use '1234567890.123456'. "
            "If not provided, sends as a new message."
        ),
    )


class SlackSenderOutputs(BaseModel):
    status: str = Field(description="Operation status message")
    channel: str = Field(description="Channel where message was sent")
    ts: str = Field(description="Message timestamp")
    message: str = Field(description="The message that was sent")


class SlackSender(Component):
    """Slack integration component for sending messages to Slack channels using OAuth."""

    TRACE_SPAN_KIND = OpenInferenceSpanKindValues.TOOL.value
    migrated = True

    @classmethod
    def get_inputs_schema(cls) -> Type[BaseModel]:
        return SlackSenderInputs

    @classmethod
    def get_outputs_schema(cls) -> Type[BaseModel]:
        return SlackSenderOutputs

    @classmethod
    def get_canonical_ports(cls) -> dict[str, str | None]:
        return {"input": "message", "output": "status"}

    def __init__(
        self,
        trace_manager: TraceManager,
        component_attributes: ComponentAttributes,
        access_token: str,
        tool_description: ToolDescription = SLACK_SENDER_TOOL_DESCRIPTION,
    ):
        """Initialize SlackSender with a provided Slack OAuth access token.

        Args:
            trace_manager: Trace manager for observability
            component_attributes: Component configuration attributes
            access_token: Slack OAuth access token (injected by OAuth processor)
            tool_description: Tool description for the component
        """
        super().__init__(
            trace_manager=trace_manager,
            tool_description=tool_description,
            component_attributes=component_attributes,
        )
        self.client = WebClient(token=access_token)

    async def _run_without_io_trace(
        self,
        inputs: SlackSenderInputs,
        ctx: dict,
    ) -> SlackSenderOutputs:
        """Send a message to a Slack channel.

        Args:
            inputs: Input parameters with channel, message, and optional thread_ts
            ctx: Execution context

        Returns:
            SlackSenderOutputs: Response with status, channel, timestamp, and message

        Raises:
            ValueError: If message or channel is not provided
            RuntimeError: If message sending fails
        """
        span = get_current_span()
        span.set_attributes({
            SpanAttributes.INPUT_VALUE: serialize_to_json(
                {"channel": inputs.channel, "message": inputs.message, "thread_ts": inputs.thread_ts},
                shorten_string=True,
            ),
        })

        try:
            LOGGER.info(f"Sending message to Slack channel {inputs.channel}")
            result = send_slack_message(
                client=self.client,
                channel=inputs.channel,
                text=inputs.message,
                thread_ts=inputs.thread_ts,
                as_markdown=True,
            )

            status_message = f"Message sent successfully to {inputs.channel}. Timestamp: {result['ts']}"
            if inputs.thread_ts:
                status_message += f" (in thread {inputs.thread_ts})"

            LOGGER.info(f"Slack message sent successfully: {result['ts']}")

            return SlackSenderOutputs(
                status=status_message,
                channel=result["channel"],
                ts=result["ts"],
                message=inputs.message,
            )

        except Exception as e:
            error_msg = f"Failed to send Slack message: {e}"
            LOGGER.error(error_msg)
            raise RuntimeError(error_msg) from e
