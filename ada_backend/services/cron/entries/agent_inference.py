"""
Agent inference cron entry: models, validators, executor, and spec.
"""

import logging
from typing import Any
from uuid import UUID

import httpx
from pydantic import Field

from ada_backend.database.models import EnvType
from ada_backend.repositories.project_repository import get_project
from ada_backend.services.cron.core import BaseExecutionPayload, BaseUserPayload, CronEntrySpec, get_cron_context
from settings import settings

LOGGER = logging.getLogger(__name__)


class AgentInferenceUserPayload(BaseUserPayload):
    """User input for agent inference cron jobs.

    TODO: If user input grows, extract to a dedicated schema module.
    """

    project_id: UUID = Field(..., description="Project ID to run the agent for")
    env: EnvType = Field(
        description="Environment (draft/production)",
        default=EnvType.PRODUCTION,
    )
    input_data: dict[str, Any] = Field(..., description="Input data for the agent")

    class Config:
        json_schema_extra = {
            "example": {
                "project_id": "123e4567-e89b-12d3-a456-426614174000",
                "env": EnvType.PRODUCTION,
                "input_data": {
                    "messages": [
                        {"role": "user", "content": "Hello, run the daily report"},
                    ]
                },
            }
        }


class AgentInferenceExecutionPayload(BaseExecutionPayload):
    """Execution payload stored in database for agent inference jobs."""

    project_id: UUID
    env: EnvType
    input_data: dict[str, Any]
    organization_id: UUID
    created_by: UUID


def validate_registration(user_input: AgentInferenceUserPayload, **kwargs) -> AgentInferenceExecutionPayload:
    """
    Validate user input and return the execution payload
    that will be used to execute the job.
    """
    # TODO: Access & consistency checks (DB):
    # - Verify organization has access to project_id
    # - Verify project exists and is active
    # - Optionally, normalize/validate input_data schema for your agent

    organization_id = kwargs.get("organization_id")
    if not organization_id:
        raise ValueError("organization_id missing from context")

    user_id = kwargs.get("user_id")
    if not user_id:
        raise ValueError("user_id missing from context")

    db = kwargs.get("db")
    if not db:
        raise ValueError("db missing from context")

    # Fetch project and validate it belongs to the organization creating the cron
    project = get_project(db, project_id=user_input.project_id)
    if not project:
        raise ValueError("Project not found")

    if project.organization_id != organization_id:
        raise ValueError("Project does not belong to the specified organization")

    return AgentInferenceExecutionPayload(
        project_id=user_input.project_id,
        env=user_input.env,
        input_data=user_input.input_data,
        organization_id=organization_id,
        created_by=user_id,
    )


def validate_execution(execution_payload: AgentInferenceExecutionPayload, **kwargs) -> None:
    """Validate execution payload and return None."""
    db = kwargs.get("db")
    if not db:
        raise ValueError("db missing from context")

    # Ensure project still exists and belongs to the same organization as when scheduled
    project = get_project(db, project_id=execution_payload.project_id)
    if not project:
        raise ValueError("Project not found at execution time")

    if project.organization_id != execution_payload.organization_id:
        raise ValueError("Project organization mismatch at execution time")


async def execute(execution_payload: AgentInferenceExecutionPayload, **kwargs) -> dict[str, Any]:
    cron_id, log_extra = get_cron_context(**kwargs)

    if not settings.ADA_URL:
        raise ValueError("ADA_URL is not configured")
    if not settings.SCHEDULER_API_KEY:
        raise ValueError("SCHEDULER_API_KEY is not configured")

    url = (
        f"{settings.ADA_URL}/internal/webhooks/projects"
        f"/{execution_payload.project_id}/envs/{execution_payload.env}/run"
    )

    LOGGER.info(
        f"Starting agent inference for project {execution_payload.project_id} in {execution_payload.env} environment",
        extra=log_extra,
    )

    async with httpx.AsyncClient() as client:
        response = await client.post(
            url,
            json=execution_payload.input_data,
            headers={
                "X-Scheduler-API-Key": settings.SCHEDULER_API_KEY,
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status()

    LOGGER.info(
        f"Agent inference accepted for project {execution_payload.project_id} (cron_id={cron_id})",
        extra=log_extra,
    )

    return {
        "status": "accepted",
        "project_id": str(execution_payload.project_id),
        "env": execution_payload.env,
    }


spec = CronEntrySpec(
    user_payload_model=AgentInferenceUserPayload,
    execution_payload_model=AgentInferenceExecutionPayload,
    registration_validator=validate_registration,
    execution_validator=validate_execution,
    executor=execute,
)
