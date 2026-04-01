import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import JSONResponse

from ada_backend.database.models import SourceType
from ada_backend.routers.auth_router import verify_ingestion_api_key_dependency
from ada_backend.schemas.ingestion_task_schema import IngestionRunRequest, SourceAttributes
from ada_backend.services.db_ingestion_service import run_db_ingestion

router = APIRouter(prefix="/internal/ingestion", tags=["Ingestion Internal"])
LOGGER = logging.getLogger(__name__)


async def _run_db_ingestion_task(
    organization_id: UUID,
    task_id: UUID,
    source_name: str,
    source_attributes: SourceAttributes,
    source_id: UUID,
) -> None:
    try:
        await run_db_ingestion(
            organization_id=organization_id,
            task_id=task_id,
            source_name=source_name,
            source_attributes=source_attributes,
            source_id=source_id,
        )
    except Exception:
        LOGGER.exception(
            "Ingestion failed for organization %s, task %s",
            organization_id,
            task_id,
        )


@router.post("/organizations/{organization_id}/run")
async def run_ingestion(
    organization_id: UUID,
    request: IngestionRunRequest,
    background_tasks: BackgroundTasks,
    verified_ingestion_api_key: Annotated[None, Depends(verify_ingestion_api_key_dependency)],
):
    if request.source_type == SourceType.DATABASE:
        background_tasks.add_task(
            _run_db_ingestion_task,
            organization_id=organization_id,
            task_id=request.task_id,
            source_name=request.source_name,
            source_attributes=request.source_attributes,
            source_id=request.source_id,
        )
        return JSONResponse(status_code=202, content={"status": "accepted"})

    return JSONResponse(
        status_code=501,
        content={"detail": f"Source type '{request.source_type.value}' is not yet supported via this endpoint"},
    )
