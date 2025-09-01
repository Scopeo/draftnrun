from typing import Annotated, List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.setup_db import get_db
from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.schemas.source_schema import DataSourceSchema, DataSourceSchemaResponse, DataSourceUpdateSchema
from ada_backend.routers.auth_router import (
    user_has_access_to_organization_dependency,
    UserRights,
    verify_ingestion_api_key_dependency,
)
from ada_backend.services.source_service import (
    get_sources_by_organization,
    create_source_by_organization,
    upsert_source_by_organization,
    delete_source_service,
    get_source_attributes_by_org_id,
)
from ada_backend.repositories.source_repository import get_data_source_by_org_id
from ada_backend.schemas.ingestion_task_schema import IngestionTaskQueue
from ada_backend.services.ingestion_task_service import create_ingestion_task_by_organization

router = APIRouter(prefix="/sources", tags=["Sources"])


@router.get("/{organization_id}", response_model=List[DataSourceSchemaResponse])
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
        return get_sources_by_organization(session, organization_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Server Error") from e


@router.post("/{organization_id}", status_code=status.HTTP_201_CREATED)
def create_organization_source(
    verified_ingestion_api_key: Annotated[None, Depends(verify_ingestion_api_key_dependency)],
    organization_id: UUID,
    source: DataSourceSchema,
    session: Session = Depends(get_db),
) -> UUID:
    try:
        source_id = create_source_by_organization(session, organization_id, source)
        return source_id
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Server Error") from e


@router.post("/{organization_id}/{source_id}", status_code=status.HTTP_200_OK)
def update_organization_source(
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.ADMIN.value))
    ],
    organization_id: UUID,
    source_id: UUID,
    session: Session = Depends(get_db),
):
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        source_attributes = get_source_attributes_by_org_id(session, organization_id, source_id)
        source_data = get_data_source_by_org_id(session, organization_id, source_id)
        ingestion_task_data = IngestionTaskQueue(
            source_name=source_data.name,
            source_type=source_data.type,
            status=db.TaskStatus.PENDING,
            source_attributes=source_attributes,
        )
        create_ingestion_task_by_organization(session, user.id, organization_id, ingestion_task_data)
        updated_source = DataSourceUpdateSchema(
            id=source_data.id,
            name=source_data.name,
            type=source_data.type,
            database_table_name=source_data.database_table_name,
            database_schema=source_data.database_schema,
            qdrant_collection_name=source_data.qdrant_collection_name,
            qdrant_schema=source_data.qdrant_schema,
            embedding_model_reference=source_data.embedding_model_reference,
            attributes=source_attributes,
        )
        return upsert_source_by_organization(session, organization_id, updated_source)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Server Error") from e


@router.delete("/{organization_id}/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_organization_source(
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
        delete_source_service(session, organization_id, source_id)
        return None
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Server Error") from e
