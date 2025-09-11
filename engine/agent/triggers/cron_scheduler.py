import logging
from datetime import datetime
from typing import Optional

from engine.agent.triggers.utils import (
    validate_cron_expression,
    validate_timezone,
    get_timezone_options,
)

from engine.agent.agent import Agent, AgentPayload, ChatMessage, ComponentAttributes, ToolDescription
from engine.trace.trace_manager import TraceManager

LOGGER = logging.getLogger(__name__)

TIMEZONE_OPTIONS = get_timezone_options()

DEFAULT_CRON_SCHEDULER_DESCRIPTION = ToolDescription(
    name="Cron_Scheduler",
    description="Schedules workflow execution based on cron expressions. "
    "Triggers the workflow automatically at specified times.",
    tool_properties={
        "cron_expression": {
            "type": "string",
            "description": "Cron expression defining when to trigger (e.g., '0 9 * * *' for daily at 9 AM)",
            "ui_component": "TEXTFIELD",
            "ui_component_properties": {
                "placeholder": "0 9 * * *",
                "description": "Format: minute hour day month day_of_week",
            },
        },
        "timezone": {
            "type": "string",
            "description": "Timezone for schedule execution. Select your local timezone "
            "to ensure schedules run at the correct time.",
            "ui_component": "SELECT",
            "ui_component_properties": {
                "options": [
                    {"value": option["value"], "label": option["label"]}
                    for region, options in TIMEZONE_OPTIONS.items()
                    for option in options
                ],
                "description": "Choose your timezone to ensure schedules run at the correct local time",
            },
        },
        "enabled": {
            "type": "boolean",
            "description": "Enable deployment in production",
            "ui_component": "CHECKBOX",
            "ui_component_properties": {"description": "Check this box to enable automatic deployment in production"},
        },
    },
    required_tool_properties=["cron_expression", "timezone"],
)


class CronScheduler(Agent):
    """
    Cron Scheduler component that triggers workflows based on cron expressions.

    In DRAFT mode: Simulates scheduled execution when user chats with workflow
    In PRODUCTION mode: Gets triggered by APScheduler at scheduled times
    """

    def __init__(
        self,
        trace_manager: TraceManager,
        tool_description: Optional[ToolDescription] = None,
        component_attributes: ComponentAttributes = None,
        cron_expression: str = "0 9 * * *",  # Default: Daily at 9 AM
        timezone: str = "UTC",
        enabled: bool = True,
        **kwargs,
    ):
        super().__init__(
            trace_manager=trace_manager,
            tool_description=tool_description or DEFAULT_CRON_SCHEDULER_DESCRIPTION,
            component_attributes=component_attributes,
            **kwargs,
        )

        # Handle parameters that might come as single-element lists from database
        if isinstance(cron_expression, list) and len(cron_expression) == 1:
            cron_expression = cron_expression[0]
        if isinstance(timezone, list) and len(timezone) == 1:
            timezone = timezone[0]
        if isinstance(enabled, list) and len(enabled) == 1:
            enabled = enabled[0]

        # Validate timezone
        timezone_validation = validate_timezone(timezone)
        if timezone_validation["status"] != "SUCCESS":
            raise ValueError(f"Invalid timezone '{timezone}': {timezone_validation['error']}")

        self.timezone = timezone
        self.timezone_label = timezone_validation["label"]

        # Validate cron expression
        cron_validation = validate_cron_expression(cron_expression)
        if cron_validation["status"] != "SUCCESS":
            raise ValueError(f"Invalid cron expression '{cron_expression}': {cron_validation['error']}")

        self.cron_expression = cron_expression
        self.cron_readable_description = cron_validation["description"]

        self.enabled = enabled

        LOGGER.info(f"CRON_SCHEDULER initialized: {self.cron_readable_description} in {self.timezone_label}")

    async def _run_without_trace(self, input_data: dict, **kwargs) -> AgentPayload:
        """
        Execute the cron scheduler.

        Behavior depends on context:
        - If input has 'scheduled': This is actual Celery execution
        - Otherwise: Regular chat/test interaction (same response)
        """
        is_scheduled = input_data.get("scheduled", False)
        triggered_at = datetime.now()

        if not self.enabled:
            content = (
                f"This cron scheduler is currently disabled.\n"
                f"Expression: {self.cron_expression}\n"
                f"Timezone: {self.timezone_label}\n"
                f"Status: Disabled"
            )
        elif is_scheduled:
            # This is actual scheduled execution from Celery
            content = (
                f"Workflow triggered by schedule at {triggered_at.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
                f"Schedule: {self.cron_expression} ({self.timezone_label})"
            )
        else:
            # Testing via Sandbox, Chat endpoint or even via the API without the scheduled flag
            content = (
                f"This workflow is scheduled to run: {self.cron_readable_description}\n"
                f"Expression: {self.cron_expression}\n"
                f"Timezone: {self.timezone_label}\n"
                f"Status: {'Enabled' if self.enabled else 'Disabled'}\n\n"
                f"In DRAFT mode: This message appears when testing\n"
                f"In PRODUCTION mode: Runs automatically at scheduled times"
            )

        return AgentPayload(
            messages=[ChatMessage(role="system", content=content)],
            artifacts={},  # Empty dict instead of None
            is_final=False,
        )
