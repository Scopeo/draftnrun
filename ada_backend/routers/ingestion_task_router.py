from typing import Annotated, List
from uuid import UUID

from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, HTTPException, status


from ada_backend.database.setup_db import get_db
from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.routers.auth_router import (
    user_has_access_to_organization_dependency,
    UserRights,
    verify_ingestion_api_key_dependency,
)
from ada_backend.services.ingestion_task_service import (
    get_ingestion_task_by_organization_id,
    create_ingestion_task_by_organization,
    upsert_ingestion_task_by_organization_id,
    delete_ingestion_task_by_id,
    update_ingestion_task_by_source_id,
)
from ada_backend.schemas.ingestion_task_schema import (
    IngestionTaskQueue,
    IngestionTaskUpdate,
    IngestionTaskResponse,
    UpdateIngestionTaskRequest,
)


router = APIRouter(prefix="/ingestion_task", tags=["Ingestion Task"])


@router.get("/{organization_id}", response_model=List[IngestionTaskResponse])
def get_organization_sources(
    organization_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.READER.value))
    ],
    session: Session = Depends(get_db),
):
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return get_ingestion_task_by_organization_id(session, organization_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Server Error") from e


@router.post("/{organization_id}", status_code=status.HTTP_201_CREATED)
def create_organization_task(
    organization_id: UUID,
    ingestion_task_data: IngestionTaskQueue,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.WRITER.value))
    ],
    session: Session = Depends(get_db),
) -> UUID:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        # Create the ingestion task
        task_id = create_ingestion_task_by_organization(session, user.id, organization_id, ingestion_task_data)
        return task_id
    except ValueError as e:
        # Handle validation errors (including duplicate source name)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Server Error") from e


@router.patch("/{organization_id}", status_code=status.HTTP_200_OK)
def update_organization_task(
    organization_id: UUID,
    verified_ingestion_api_key: Annotated[None, Depends(verify_ingestion_api_key_dependency)],
    ingestion_task_data: IngestionTaskUpdate,
    session: Session = Depends(get_db),
):
    try:
        upsert_ingestion_task_by_organization_id(session, organization_id, ingestion_task_data)
        return None
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Server Error") from e


@router.patch("/{organization_id}/sources/{source_id}/tasks", status_code=status.HTTP_200_OK)
def update_ingestion_task_by_source(
    organization_id: UUID,
    source_id: UUID,
    update_request: UpdateIngestionTaskRequest,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.WRITER.value))
    ],
    session: Session = Depends(get_db),
) -> dict:
    """
    Update ingestion task for a specific source with new files/folders.

    This endpoint creates a new ingestion task linked to the existing source
    and triggers re-ingestion with the provided files or folder.
    """
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    try:
        task_id = update_ingestion_task_by_source_id(session, organization_id, source_id, update_request)
        return {
            "message": "Ingestion task updated successfully",
            "task_id": str(task_id),
            "source_id": str(source_id),
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Server Error") from e


@router.delete("/{organization_id}/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_organization_task(
    organization_id: UUID,
    source_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.ADMIN.value))
    ],
    session: Session = Depends(get_db),
):
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        delete_ingestion_task_by_id(session, organization_id, source_id)
        return None
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Server Error") from e
