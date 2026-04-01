import logging
from typing import Annotated, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ada_backend.database.models import EnvType
from ada_backend.database.setup_db import get_db
from ada_backend.routers.auth_router import verify_api_key_dependency
from ada_backend.schemas.auth_schema import VerifiedApiKey
from ada_backend.schemas.webhook_schema import WebhookProcessingResponseSchema
from ada_backend.services.webhooks.errors import WebhookServiceError
from ada_backend.services.webhooks.webhook_service import process_direct_trigger_event

router = APIRouter(prefix="/webhooks/trigger", tags=["Webhooks Trigger"])
LOGGER = logging.getLogger(__name__)


@router.post("/{project_id}/envs/{env}", response_model=WebhookProcessingResponseSchema, status_code=202)
async def trigger_workflow_webhook(
    project_id: UUID,
    env: EnvType,
    payload: dict = Body(default_factory=dict),
    event_id: Optional[str] = Query(
        None,
        description="Optional idempotency key. If not provided, one is auto-generated.",
    ),
    session: Session = Depends(get_db),
    verified_api_key: Annotated[VerifiedApiKey, Depends(verify_api_key_dependency)] = None,
) -> WebhookProcessingResponseSchema:
    """
    Trigger a workflow run via webhook. Returns 202 immediately and processes
    the run asynchronously via the Redis webhook queue.

    Authentication: X-API-Key header (same project-scoped key used for the run endpoint).
    """
    if verified_api_key.project_id != project_id:
        raise HTTPException(status_code=403, detail="You don't have access to this project")

    try:
        return await process_direct_trigger_event(
            session=session,
            project_id=project_id,
            env=env.value,
            payload=payload,
            event_id=event_id or str(uuid4()),
        )
    except WebhookServiceError as e:
        LOGGER.error(f"Failed to process direct trigger for project {project_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=503, detail="Failed to queue workflow run. Please try again.") from e
