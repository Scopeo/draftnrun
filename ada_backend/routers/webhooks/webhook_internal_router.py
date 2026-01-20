import logging
from typing import Annotated, Any, Dict, List
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from ada_backend.database.models import CallType, EnvType
from ada_backend.database.setup_db import get_db
from ada_backend.routers.auth_router import verify_webhook_api_key_dependency
from ada_backend.schemas.project_schema import ChatResponse
from ada_backend.schemas.webhook_schema import IntegrationTriggerResponse
from ada_backend.services.agent_runner_service import run_env_agent
from ada_backend.services.errors import EnvironmentNotFound, MissingDataSourceError
from ada_backend.services.webhooks.webhook_service import get_webhook_triggers_service

router = APIRouter(prefix="/internal/webhooks", tags=["Webhooks Internal"])
LOGGER = logging.getLogger(__name__)


@router.get("/{webhook_id}/triggers", response_model=List[IntegrationTriggerResponse])
async def get_webhook_triggers_endpoint(
    webhook_id: UUID,
    session: Session = Depends(get_db),
    verified_webhook_api_key: Annotated[None, Depends(verify_webhook_api_key_dependency)] = None,
) -> List[IntegrationTriggerResponse]:
    """
    Get all enabled integration triggers for a webhook.
    Internal endpoint for webhook workers, requires webhook API key.
    """
    try:
        return get_webhook_triggers_service(session=session, webhook_id=webhook_id)
    except Exception as e:
        LOGGER.error(f"Failed to get triggers for webhook {webhook_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/projects/{project_id}/run", response_model=ChatResponse)
async def run_workflow_internal(
    project_id: UUID,
    input_data: Dict[str, Any] = Body(...),
    session: Session = Depends(get_db),
    verified_webhook_api_key: Annotated[None, Depends(verify_webhook_api_key_dependency)] = None,
) -> ChatResponse:
    """
    Run a workflow/agent for a project.
    Internal endpoint for webhook workers, requires webhook API key.
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
    except Exception as e:
        LOGGER.error(f"Failed to run workflow for project {project_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e
