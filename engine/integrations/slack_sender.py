import logging
from typing import Optional

from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
from opentelemetry.trace import get_current_span

from engine.agent.agent import AgentPayload, ChatMessage, ComponentAttributes, ToolDescription
from engine.agent.agent import Agent
from engine.integrations.slack_utils import get_slack_client, send_slack_message
from engine.trace.trace_manager import TraceManager
from settings import settings

LOGGER = logging.getLogger(__name__)

SLACK_SENDER_TOOL_DESCRIPTION = ToolDescription(
    name="Slack Sender",
    description="A tool to send messages to Slack channels using bot token.",
    tool_properties={
        "channel": {
            "type": "string",
            "description": "Channel name or ID to send message to (e.g., #general or C1234567890)",
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


class SlackSender(Agent):
    TRACE_SPAN_KIND = OpenInferenceSpanKindValues.TOOL.value

    def __init__(
        self,
        trace_manager: TraceManager,
        component_attributes: ComponentAttributes,
        bot_token: str,
        default_channel: Optional[str] = None,
        tool_description: ToolDescription = SLACK_SENDER_TOOL_DESCRIPTION,
    ):
        super().__init__(
            trace_manager,
            tool_description=tool_description,
            component_attributes=component_attributes,
        )

        # Simple parameter-based approach
        if not bot_token:
            # Fall back to environment variable if no token provided
            if not settings.SLACK_BOT_TOKEN:
                raise ValueError("SLACK_BOT_TOKEN not configured in environment")
            bot_token = settings.SLACK_BOT_TOKEN

        self.client = get_slack_client(bot_token)
        self.default_channel = default_channel

    async def _run_without_trace(
        self,
        *inputs: AgentPayload,
        channel: Optional[str] = None,
        message: Optional[str] = None,
        thread_ts: Optional[str] = None,
    ) -> AgentPayload:
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
            )

            output_message = f"Message sent successfully to {target_channel}. Timestamp: {result['ts']}"
            if thread_ts:
                output_message += f" (in thread {thread_ts})"

            LOGGER.info(f"Slack message sent successfully: {result['ts']}")

            return AgentPayload(messages=[ChatMessage(role="assistant", content=output_message)])

        except Exception as e:
            error_msg = f"Failed to send Slack message: {e}"
            LOGGER.error(error_msg)
            raise RuntimeError(error_msg)
