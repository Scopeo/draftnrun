import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ada_backend.database.setup_db import get_db, get_db_session
from ada_backend.routers.auth_router import verify_scheduler_api_key_dependency
from ada_backend.services.cron.endpoint_polling_service import run_endpoint_polling
from ada_backend.services.cron.entries.endpoint_polling import EndpointPollingExecutionPayload
from settings import settings

router = APIRouter(prefix="/internal/scheduler", tags=["Scheduler Internal"])
LOGGER = logging.getLogger(__name__)


class EndpointPollingRunBody(BaseModel):
    cron_id: UUID
    payload: EndpointPollingExecutionPayload


async def _run_endpoint_polling_background(cron_id: UUID, payload: EndpointPollingExecutionPayload) -> None:
    with get_db_session() as db:
        try:
            await run_endpoint_polling(
                cron_id=cron_id,
                payload=payload,
                db=db,
                ada_url=settings.ADA_URL,
                scheduler_api_key=settings.SCHEDULER_API_KEY,
            )
        except Exception as e:
            LOGGER.error(
                f"Endpoint polling background task failed for cron_id={cron_id}: {e}",
                exc_info=True,
            )


@router.post("/endpoint-polling/run", status_code=202)
async def run_endpoint_polling_endpoint(
    body: EndpointPollingRunBody,
    background_tasks: BackgroundTasks,
    verified: Annotated[None, Depends(verify_scheduler_api_key_dependency)] = None,
) -> dict:
    """
    Trigger an endpoint polling run as a background task.
    Returns 202 immediately. The full poll → diff → trigger loop runs asynchronously.
    Internal endpoint called by the scheduler. Requires X-Scheduler-API-Key.
    """
    background_tasks.add_task(_run_endpoint_polling_background, body.cron_id, body.payload)
    return {"status": "accepted"}
