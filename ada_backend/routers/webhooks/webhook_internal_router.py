import json
import logging
from typing import Annotated, Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from ada_backend.database.models import CallType, EnvType
from ada_backend.database.setup_db import get_db, get_db_session
from ada_backend.routers.auth_router import (
    verify_webhook_api_key_dependency,
    verify_webhook_or_scheduler_api_key_dependency,
)
from ada_backend.schemas.project_schema import ChatResponse
from ada_backend.schemas.webhook_schema import (
    IntegrationTriggerResponse,
    WebhookExecuteBody,
    WebhookExecuteResponse,
)
from ada_backend.services.agent_runner_service import run_env_agent
from ada_backend.services.errors import EnvironmentNotFound, MissingDataSourceError, MissingIntegrationError
from ada_backend.services.webhooks.webhook_service import (
    execute_webhook,
    get_webhook_triggers_service,
)

router = APIRouter(prefix="/internal/webhooks", tags=["Webhooks Internal"])
LOGGER = logging.getLogger(__name__)


@router.post("/{webhook_id}/execute", response_model=WebhookExecuteResponse)
async def execute_webhook_endpoint(
    webhook_id: UUID,
    body: WebhookExecuteBody,
    session: Session = Depends(get_db),
    verified_webhook_api_key: Annotated[None, Depends(verify_webhook_api_key_dependency)] = None,
) -> WebhookExecuteResponse:
    """
    Get triggers for the webhook, prepare workflow input (provider-specific),
    and run the workflow for each trigger. Internal endpoint for webhook workers.
    """
    return await execute_webhook(
        session=session,
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


async def _run_project_background(project_id: UUID, env: EnvType, input_data: Dict[str, Any]) -> None:
    # TODO: add to redis queue. currently will hold all sessions open until end of runs
    with get_db_session() as session:
        try:
            await run_env_agent(
                session=session,
                project_id=project_id,
                input_data=input_data,
                env=env,
                call_type=CallType.API,
            )
        except EnvironmentNotFound as e:
            LOGGER.error(f"Environment not found for project {project_id} env={env}: {str(e)}", exc_info=True)
        except MissingDataSourceError as e:
            LOGGER.error(f"Data source not found for project {project_id} env={env}: {str(e)}", exc_info=True)
        except MissingIntegrationError as e:
            LOGGER.error(f"Missing integration for project {project_id} env={env}: {str(e)}", exc_info=True)
        except Exception as e:
            LOGGER.error(f"Failed to run workflow for project {project_id} env={env}: {str(e)}", exc_info=True)


@router.post("/projects/{project_id}/envs/{env}/run", status_code=202)
async def run_project_internal(
    project_id: UUID,
    env: EnvType,
    background_tasks: BackgroundTasks,
    input_data: Dict[str, Any] = Body(...),
    verified_key: Annotated[None, Depends(verify_webhook_or_scheduler_api_key_dependency)] = None,
) -> dict:
    """
    Enqueue a workflow/agent run for a project at a given environment.
    Returns 202 immediately and executes the run as a background task.
    Internal endpoint called by the webhook worker for direct trigger events.
    Requires X-Webhook-API-Key.
    """
    background_tasks.add_task(_run_project_background, project_id=project_id, env=env, input_data=input_data)
    return {"status": "accepted"}


@router.post(
    "/projects/{project_id}/run",
    response_model=ChatResponse,
    deprecated=True,
)
async def run_workflow_internal(
    project_id: UUID,
    input_data: Dict[str, Any] = Body(...),
    session: Session = Depends(get_db),
    verified_webhook_api_key: Annotated[None, Depends(verify_webhook_api_key_dependency)] = None,
) -> ChatResponse:
    """
    Run a workflow/agent for a project.
    Internal endpoint for webhook workers, requires webhook API key.
    Deprecated: use POST /internal/webhooks/{webhook_id}/execute instead.
    """
    try:
        return await run_env_agent(
            session=session,
            project_id=project_id,
            input_data=input_data,
            env=EnvType.PRODUCTION,
            call_type=CallType.API,
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
