import json
import logging
from typing import Annotated, Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ada_backend.database.models import CallType, EnvType, RunStatus
from ada_backend.database.setup_db import get_db
from ada_backend.routers.auth_router import (
    verify_webhook_api_key_dependency,
    verify_webhook_or_scheduler_api_key_dependency,
)
from ada_backend.schemas.project_schema import ChatResponse
from ada_backend.schemas.webhook_schema import (
    IntegrationTriggerResponse,
    RunProjectBody,
    WebhookExecuteBody,
    WebhookExecuteResponse,
)
from ada_backend.services.agent_runner_service import run_env_agent
from ada_backend.services.errors import (
    EnvironmentNotFound,
    InvalidRunStatusTransition,
    MissingDataSourceError,
    MissingIntegrationError,
    RunNotFound,
)
from ada_backend.services.run_service import create_run, fail_pending_run, run_with_tracking, update_run_status
from ada_backend.services.webhooks.webhook_service import (
    execute_webhook,
    get_webhook_triggers_service,
)
from ada_backend.utils.redis_client import push_run_task

router = APIRouter(prefix="/internal/webhooks", tags=["Webhooks Internal"])
LOGGER = logging.getLogger(__name__)


@router.post("/{webhook_id}/execute", response_model=WebhookExecuteResponse)
async def execute_webhook_endpoint(
    webhook_id: UUID,
    body: WebhookExecuteBody,
    verified_webhook_api_key: Annotated[None, Depends(verify_webhook_api_key_dependency)] = None,
) -> WebhookExecuteResponse:
    """
    Get triggers for the webhook, prepare workflow input (provider-specific),
    and run the workflow for each trigger. Internal endpoint for webhook workers.
    """
    return await execute_webhook(
        webhook_id=webhook_id,
        provider=body.provider,
        event_id=body.event_id,
        payload=body.payload,
    )


@router.get(
    "/{webhook_id}/triggers",
    response_model=List[IntegrationTriggerResponse],
    deprecated=True,
)
async def get_webhook_triggers_endpoint(
    webhook_id: UUID,
    provider: Optional[str] = None,
    webhook_event_data: Optional[str] = None,
    session: Session = Depends(get_db),
    verified_webhook_api_key: Annotated[None, Depends(verify_webhook_api_key_dependency)] = None,
) -> List[IntegrationTriggerResponse]:
    """
    Get all enabled integration triggers for a webhook.
    Optionally filters triggers based on provider and payload data.
    Internal endpoint for webhook workers, requires webhook API key.
    Deprecated: triggers are resolved inside POST /internal/webhooks/{webhook_id}/execute.
    """
    try:
        event_data = json.loads(webhook_event_data)

        return get_webhook_triggers_service(
            session=session, webhook_id=webhook_id, provider=provider, event_data=event_data
        )
    except Exception as e:
        LOGGER.error(f"Failed to get triggers for webhook {webhook_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/projects/{project_id}/envs/{env}/run", status_code=202)
async def run_project_internal(
    project_id: UUID,
    env: EnvType,
    body: RunProjectBody = Body(...),
    run_id: Optional[UUID] = Query(None, description="Pre-created run ID to reuse instead of creating a new one"),
    event_id: Optional[str] = Query(None, description="Webhook event ID for run tracking"),
    session: Session = Depends(get_db),
    verified_key: Annotated[str, Depends(verify_webhook_or_scheduler_api_key_dependency)] = None,
) -> dict:
    """
    Enqueue a workflow/agent run to the durable Redis run queue.
    Returns 202 immediately with run_id; the RunQueueWorker picks up and executes
    the run with heartbeat-based orphan recovery.
    Internal endpoint called by the webhook worker or the scheduler.
    Requires X-Webhook-API-Key or X-Scheduler-API-Key.

    If run_id is provided, reuses the existing PENDING run row (created before enqueue).
    """
    trigger = CallType.WEBHOOK if verified_key == "webhook" else CallType.CRON

    if run_id is None:
        run = create_run(
            session=session,
            project_id=project_id,
            trigger=trigger,
            event_id=event_id,
            env=env,
        )
        run_id = run.id

    pushed = push_run_task(
        run_id=run_id,
        project_id=project_id,
        env=env.value,
        input_data=body.input_data,
        trigger=trigger.value,
        cron_id=body.cron_id,
        cron_run_id=body.cron_run_id,
    )
    if not pushed:
        update_run_status(
            session,
            run_id=run_id,
            project_id=project_id,
            status=RunStatus.FAILED,
            error={"message": "Failed to enqueue run; Redis unavailable.", "type": "EnqueueError"},
        )
        raise HTTPException(
            status_code=503,
            detail="Run created but could not be enqueued. Try again later.",
        )

    return {"status": "accepted", "run_id": str(run_id)}


@router.patch("/projects/{project_id}/runs/{run_id}/fail", status_code=200)
async def fail_run_internal(
    project_id: UUID,
    run_id: UUID,
    body: Dict[str, Any] = Body(...),
    session: Session = Depends(get_db),
    verified_webhook_api_key: Annotated[None, Depends(verify_webhook_api_key_dependency)] = None,
) -> dict:
    """
    Mark a pre-created PENDING run as FAILED. Called by the webhook worker when a message
    is dead-lettered (repeated crashes before execution could start).
    Returns 409 if the run is no longer pending (already picked up by another worker).
    """
    error = body.get("error", {"message": "Unknown failure", "type": "DeadLetter"})
    try:
        fail_pending_run(session, run_id=run_id, error=error, project_id=project_id)
    except RunNotFound:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    except InvalidRunStatusTransition:
        raise HTTPException(status_code=409, detail=f"Run {run_id} is not in pending status")
    return {"status": "failed", "run_id": str(run_id)}


@router.post(
    "/projects/{project_id}/run",
    response_model=ChatResponse,
    deprecated=True,
)
async def run_workflow_internal(
    project_id: UUID,
    input_data: Dict[str, Any] = Body(...),
    verified_webhook_api_key: Annotated[None, Depends(verify_webhook_api_key_dependency)] = None,
) -> ChatResponse:
    """
    Run a workflow/agent for a project.
    Internal endpoint for webhook workers, requires webhook API key.
    Deprecated: use POST /internal/webhooks/{webhook_id}/execute instead.
    """
    env = EnvType.PRODUCTION
    try:
        return await run_with_tracking(
            project_id=project_id,
            trigger=CallType.WEBHOOK,
            env=env,
            runner_coro=run_env_agent(
                project_id=project_id,
                input_data=input_data,
                env=env,
                call_type=CallType.WEBHOOK,
            ),
        )
    except EnvironmentNotFound as e:
        LOGGER.error(f"Environment not found for project {project_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=404, detail=str(e)) from e
    except MissingDataSourceError as e:
        LOGGER.error(f"Data source not found for project {project_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=404, detail=str(e)) from e
    except MissingIntegrationError as e:
        LOGGER.error(f"Missing integration for project {project_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        LOGGER.error(f"Failed to run workflow for project {project_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e
