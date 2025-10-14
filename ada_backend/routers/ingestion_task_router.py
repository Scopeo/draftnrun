from typing import Annotated, List
from uuid import UUID
import logging

from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, HTTPException, status


from ada_backend.database.setup_db import get_db
from ada_backend.schemas.auth_schema import SupabaseUser, VerifiedApiKey
from ada_backend.routers.auth_router import (
    user_has_access_to_organization_dependency,
    UserRights,
    verify_api_key_dependency,
    verify_ingestion_api_key_dependency,
    user_has_access_to_organization_or_verify_api_key,
)
from ada_backend.services.ingestion_task_service import (
    get_ingestion_task_by_organization_id,
    create_ingestion_task_by_organization,
    upsert_ingestion_task_by_organization_id,
    delete_ingestion_task_by_id,
)
from ada_backend.schemas.ingestion_task_schema import (
    IngestionTaskQueue,
    IngestionTaskUpdate,
    IngestionTaskResponse,
)


LOGGER = logging.getLogger(__name__)


router = APIRouter(tags=["Ingestion Task"])


@router.get("/ingestion_task/{organization_id}", response_model=List[IngestionTaskResponse])
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
        LOGGER.error(f"Failed to get ingestion tasks for organization {organization_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/ingestion_task/{organization_id}", status_code=status.HTTP_201_CREATED)
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
        task_id = create_ingestion_task_by_organization(
            session, organization_id=organization_id, ingestion_task_data=ingestion_task_data, user_id=user.id
        )
        return task_id
    except Exception as e:
        LOGGER.error(f"Failed to create ingestion task for organization {organization_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/organizations/{organization_id}/ingestion_tasks/api-key-auths", status_code=status.HTTP_201_CREATED)
def create_ingestion_task_with_api_key(
    organization_id: UUID,
    ingestion_task_data: IngestionTaskQueue,
    verified_api_key: VerifiedApiKey = Depends(verify_api_key_dependency),
    session: Session = Depends(get_db),
):
    if verified_api_key.organization_id != organization_id:
        raise HTTPException(status_code=403, detail="You don't have access to this organization")
    try:
        task_id = create_ingestion_task_by_organization(
            session,
            organization_id=organization_id,
            ingestion_task_data=ingestion_task_data,
            api_key_id=verified_api_key.api_key_id,
        )
        return task_id
    except Exception as e:
        LOGGER.error(
            f"Failed to create ingestion task for organization {organization_id} via API key: {str(e)}", exc_info=True
        )
        raise HTTPException(status_code=500, detail="Internal server error") from e


# New unified endpoint that supports both authentication methods
@router.post("/ingestion_task/{organization_id}/unified", status_code=status.HTTP_201_CREATED)
def create_ingestion_task_unified(
    organization_id: UUID,
    ingestion_task_data: IngestionTaskQueue,
    auth_ids: Annotated[tuple[UUID | None, UUID | None], Depends(user_has_access_to_organization_or_verify_api_key)],
    session: Session = Depends(get_db),
) -> UUID:
    user_id, api_key_id = auth_ids
    try:
        task_id = create_ingestion_task_by_organization(
            session,
            organization_id=organization_id,
            ingestion_task_data=ingestion_task_data,
            user_id=user_id,
            api_key_id=api_key_id,
        )
        return task_id
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Server Error") from e


@router.patch("/ingestion_task/{organization_id}", status_code=status.HTTP_200_OK)
def update_organization_task(
    organization_id: UUID,
    verified_ingestion_api_key: Annotated[None, Depends(verify_ingestion_api_key_dependency)],
    ingestion_task_data: IngestionTaskUpdate,
    session: Session = Depends(get_db),
):
    try:
        upsert_ingestion_task_by_organization_id(
            session, organization_id=organization_id, ingestion_task_data=ingestion_task_data
        )
        return None
    except Exception as e:
        LOGGER.error(f"Failed to update ingestion task for organization {organization_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.delete("/ingestion_task/{organization_id}/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
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
        delete_ingestion_task_by_id(session, organization_id=organization_id, id=source_id)
        return None
    except Exception as e:
        LOGGER.error(
            f"Failed to delete ingestion task {source_id} for organization {organization_id}: {str(e)}", exc_info=True
        )
        raise HTTPException(status_code=500, detail="Internal server error") from e
