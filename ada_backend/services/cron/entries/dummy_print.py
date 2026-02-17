"""
Dummy print cron entry: models, validators, executor, and spec.
"""

import logging
import random
from datetime import datetime, timezone
from uuid import UUID

from pydantic import Field

from ada_backend.services.cron.core import BaseExecutionPayload, BaseUserPayload, CronEntrySpec, get_cron_context

LOGGER = logging.getLogger(__name__)


class DummyPrintUserPayload(BaseUserPayload):
    """User input for dummy print cron jobs."""

    message: str = Field(..., description="Message to print")
    error_rate: float = Field(default=0.0, ge=0.0, le=1.0, description="Simulated error rate (0.0-1.0)")

    class Config:
        json_schema_extra = {
            "example": {
                "message": "Hello from cron job!",
                "error_rate": 0.1,
            }
        }


class DummyPrintExecutionPayload(BaseExecutionPayload):
    """Execution payload stored in database for dummy print jobs."""

    message: str
    error_rate: float
    organization_id: UUID
    user_id: UUID


def validate_registration(
    user_input: DummyPrintUserPayload,
    organization_id: UUID,
    user_id: UUID,
    **kwargs,
) -> DummyPrintExecutionPayload:
    if not user_input.message.strip():
        raise ValueError("message cannot be empty or whitespace-only")

    if not organization_id:
        raise ValueError("organization_id missing")

    return DummyPrintExecutionPayload(
        message=user_input.message,
        error_rate=user_input.error_rate,
        organization_id=organization_id,
        user_id=user_id,
    )


def validate_execution(execution_payload: DummyPrintExecutionPayload, **kwargs) -> None:
    if not execution_payload.message.strip():
        raise ValueError("message cannot be empty at execution time")


async def execute(execution_payload: DummyPrintExecutionPayload, **kwargs) -> dict[str, object]:
    cron_id, log_extra = get_cron_context(**kwargs)

    LOGGER.info("Starting dummy cron job execution", extra=log_extra)

    # Simulate a failure based on the error rate
    if random.random() < execution_payload.error_rate:
        error_msg = f"Simulated random failure! (Error rate: {execution_payload.error_rate})"
        LOGGER.warning(f"Dummy cron job simulated failure: {error_msg}", extra=log_extra)
        raise ValueError(error_msg)

    # Execute the dummy task
    current_time = datetime.now(timezone.utc).isoformat()
    LOGGER.info(f"Dummy cron job executed with message: '{execution_payload.message}'", extra=log_extra)

    return {
        "message_printed": execution_payload.message,
        "executed_at": current_time,
        "error_rate": execution_payload.error_rate,
    }


spec = CronEntrySpec(
    user_payload_model=DummyPrintUserPayload,
    execution_payload_model=DummyPrintExecutionPayload,
    registration_validator=validate_registration,
    execution_validator=validate_execution,
    executor=execute,
)
